package no.fugleramme.kamera

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.util.Range
import android.util.Size
import android.view.Surface
import androidx.activity.ComponentActivity
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Fuglekameraet: overvaaker hagen med hovedkameraet (1x) og tar bildet med
 * telelinsen (5x) naar bevegelsen er ved materen.
 *
 * Bevegelsen maales som i kamera/kamera.py. Det som sendes er et kvadratisk
 * utsnitt rundt fuglen i full opploesning, ikke hele bildet: serveren
 * krymper alt til 768 px foer modellen ser det, og hele hagen i 768 px gjoer
 * en spettmeis til 10-15 px.
 *
 * Ved materen tas foerst et 1x-bilde i reserve. Saa bytter kameraet til
 * telelinsen og ser etter bevegelse der i noen sekunder; finner det den, tas
 * telebildet rundt den. Er fuglen borte for linsebyttet, sendes 1x-bildet.
 *
 * All tilstand lever paa én traad (traad); kameraets tilbakekall kommer dit.
 */
@OptIn(markerClass = [ExperimentalCamera2Interop::class])
class Fuglekamera(private val aktivitet: ComponentActivity, private val mappe: File) {

    private enum class Tilstand { OVERVAAK, OPPTATT, TELE_VENT, TELE_LET }

    /** Et bilde fra kameraet, i sensorens retning, med det som trengs for aa snu og beskrive det. */
    private class Tatt(
        val jpeg: ByteArray, val grader: Int, val bredde: Int, val hoeyde: Int,
        val tidNs: Long?, val iso: Int?, val rask: Boolean,
        val fysisk: String?, val linse: String, val zoom: Float,
    )

    private class Reserve(val jpeg: ByteArray, val meta: JSONObject)

    private val traad = Executors.newSingleThreadScheduledExecutor()
    private val sender = Sender(mappe)
    private val konfigFil = File(mappe, "kamera.json")
    // Legges der av kjor.sh titt: et helt bilde med feltene tegnet inn -> siste.jpg.
    private val flagg = File(mappe, "TA_BILDE")

    private var k = Konfig()
    private var konfigTid = 0L
    private var kamera: Camera? = null
    private var analyse: ImageAnalysis? = null
    private var bildetaker: ImageCapture? = null
    // Hvilken vei telefonen henger, som Surface.ROTATION_*; settes av aktiviteten
    // fra akselerometeret. Kameraet snur bildene etter den.
    @Volatile private var maalRotasjon = Surface.ROTATION_90
    private var linser = mapOf<String, String>()
    private var isoOmraade: Range<Int>? = null
    private var boostOmraade: Range<Int>? = null
    private var fpsOmraade: Range<Int>? = null

    private var tilstand = Tilstand.OVERVAAK
    private var opptattSiden = 0L
    private var forrige: Graa? = null
    private var paaRad = 0
    private var sistHendelse = -1_000_000L
    private var sisteRamme = 0L
    private var natt = false
    private var nattTil = 0L
    private var teleVentTil = 0L
    private var teleFrist = 0L
    private var teleFelt = Felt.HELE
    private var reserve: Reserve? = null
    private var sistTitt = 0L
    private var sisteLys = 0.0
    private var sisteMaal = Maal(0.0, 0, null)
    private var sisteKlynge: Felt? = null

    // Siste tall fra kameraet, satt paa kameraets egen traad.
    @Volatile private var aeTidNs: Long? = null
    @Volatile private var aeIso: Int? = null
    @Volatile private var aeBoost: Int? = null
    @Volatile private var aktivLinse: String? = null
    @Volatile private var fokus: Float? = null

    // Til skjermen: kalles bare mens den vises.
    @Volatile var guiSynlig = false
    @Volatile var visning: ((Graa, List<Felt>, Felt?, Felt?, String) -> Unit)? = null

    fun start() {
        k = lesKonfig()
        konfigTid = konfigFil.lastModified()
        Logg.skriv("starter: send ${if (k.send) "til ${k.server}" else "av"}, felt ${k.roier.map { it.json() }}, " +
            "tele ${if (k.tele) "i ${k.teleSone.json()}" else "av"}, roter ${k.roter}")
        val fremtid = ProcessCameraProvider.getInstance(aktivitet)
        fremtid.addListener({ bind(fremtid.get()) }, aktivitet.mainExecutor)
    }

    /**
     * Telefonen henger en ny vei. Kameraet oppgir rotasjonen i forhold til
     * denne, saa bildene og feltene staar riktig vei uansett hvordan den
     * henger. Forrige ramme er snudd annerledes og kan ikke sammenlignes.
     */
    fun settRotasjon(r: Int) {
        if (r == maalRotasjon) return
        maalRotasjon = r
        analyse?.targetRotation = r
        bildetaker?.targetRotation = r
        traad.execute {
            forrige = null
            paaRad = 0
        }
        val hvordan = when (r) {
            Surface.ROTATION_0 -> "paa hoeykant"
            Surface.ROTATION_180 -> "paa hoeykant, opp ned"
            Surface.ROTATION_90 -> "liggende, toppen mot venstre"
            else -> "liggende, toppen mot hoeyre"
        }
        Logg.skriv("telefonen henger $hvordan; bildene snus etter det")
    }

    private fun bind(leverandoer: ProcessCameraProvider) {
        val rotasjon = maalRotasjon
        val fireTreDeler = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
        val analyseBygger = ImageAnalysis.Builder()
            .setResolutionSelector(fireTreDeler.setResolutionStrategy(ResolutionStrategy(
                Size(k.analyseBredde, k.analyseBredde * 3 / 4),
                ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)).build())
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
            .setTargetRotation(rotasjon)
        Camera2Interop.Extender(analyseBygger).setSessionCaptureCallback(
            object : CameraCaptureSession.CaptureCallback() {
                override fun onCaptureCompleted(
                    session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult,
                ) {
                    // Autoeksponeringens valg er grunnlaget for rask lukker;
                    // rammene med manuell eksponering skal ikke overskrive det.
                    if (result.get(CaptureResult.CONTROL_AE_MODE) != CaptureResult.CONTROL_AE_MODE_OFF) {
                        aeTidNs = result.get(CaptureResult.SENSOR_EXPOSURE_TIME)
                        aeIso = result.get(CaptureResult.SENSOR_SENSITIVITY)
                        aeBoost = result.get(CaptureResult.CONTROL_POST_RAW_SENSITIVITY_BOOST)
                    }
                    aktivLinse = result.get(CaptureResult.LOGICAL_MULTI_CAMERA_ACTIVE_PHYSICAL_ID)
                    fokus = result.get(CaptureResult.LENS_FOCUS_DISTANCE)
                }
            })
        val analyse = analyseBygger.build()
        analyse.setAnalyzer(traad) { ramme(it) }
        this.analyse = analyse
        val taker = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .setResolutionSelector(ResolutionSelector.Builder()
                .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY)
                .build())
            .setTargetRotation(rotasjon)
            .setJpegQuality(95)
            .build()
        leverandoer.unbindAll()
        val kam = leverandoer.bindToLifecycle(aktivitet, CameraSelector.DEFAULT_BACK_CAMERA, analyse, taker)
        kamera = kam
        bildetaker = taker
        val info = Camera2CameraInfo.from(kam.cameraInfo)
        isoOmraade = info.getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_SENSITIVITY_RANGE)
        boostOmraade = info.getCameraCharacteristic(CameraCharacteristics.CONTROL_POST_RAW_SENSITIVITY_BOOST_RANGE)
        fpsOmraade = info.getCameraCharacteristic(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)
            ?.firstOrNull { it.lower == k.fps && it.upper == k.fps }
        linser = linsenavn(info.cameraId)
        settGrunnvalg()
        kam.cameraInfo.cameraState.observe(aktivitet) { s ->
            s.error?.let { Logg.skriv("kamerafeil: kode ${it.code} (${s.type})") }
        }
        Logg.skriv("kamera ${info.cameraId}: analyse ${analyse.resolutionInfo?.resolution}, " +
            "bilde ${taker.resolutionInfo?.resolution}, fps ${fpsOmraade ?: "kameraets valg"}, linser $linser")
    }

    /** Fysiske kameraer bak det logiske, med navn etter brennvidden. */
    private fun linsenavn(logisk: String): Map<String, String> {
        val cm = aktivitet.getSystemService(CameraManager::class.java)
        return cm.getCameraCharacteristics(logisk).physicalCameraIds.associateWith { id ->
            val f = cm.getCameraCharacteristics(id)
                .get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)?.firstOrNull() ?: 0f
            when {
                f > 10f -> "tele"
                f > 4f -> "hoved"
                else -> "vid"
            }
        }
    }

    private fun aktivLinsenavn() = aktivLinse?.let { linser[it] ?: it } ?: "?"

    /** Det som alltid gjelder: bilderate og eventuelt fast fokus. */
    private fun grunnvalg(): CaptureRequestOptions.Builder {
        val b = CaptureRequestOptions.Builder()
        fpsOmraade?.let { b.setCaptureRequestOption(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, it) }
        if (k.fokusM > 0) {
            b.setCaptureRequestOption(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_OFF)
            b.setCaptureRequestOption(CaptureRequest.LENS_FOCUS_DISTANCE, (1.0 / k.fokusM).toFloat())
        }
        return b
    }

    private fun settGrunnvalg() {
        val kam = kamera ?: return
        Camera2CameraControl.from(kam.cameraControl).setCaptureRequestOptions(grunnvalg().build())
    }

    // ------------------------------------------------------------------
    // Rammene
    // ------------------------------------------------------------------

    private fun ramme(bilde: ImageProxy) {
        try {
            val naa = SystemClock.elapsedRealtime()
            val tele = tilstand == Tilstand.TELE_VENT || tilstand == Tilstand.TELE_LET
            val intervall = if (tele) 250L else (k.rammeS * 1000).toLong()
            if (naa - sisteRamme < intervall) return
            sisteRamme = naa
            if (tilstand == Tilstand.OPPTATT) {
                if (naa - opptattSiden > 20_000) {
                    Logg.skriv("bildetakingen svarte ikke paa 20 s; starter overvaakingen paa nytt")
                    nullstill(pause = true)
                }
                return
            }
            sjekkKonfig()
            val g = graaFra(bilde, (bilde.imageInfo.rotationDegrees + k.roter) % 360)
            when (tilstand) {
                Tilstand.OVERVAAK -> overvaak(g, naa)
                Tilstand.TELE_VENT -> if (naa >= teleVentTil) {
                    tilstand = Tilstand.TELE_LET
                    teleFrist = naa + (k.teleLetingS * 1000).toLong()
                    forrige = g
                }
                Tilstand.TELE_LET -> letTele(g, naa)
                Tilstand.OPPTATT -> {}
            }
            if (guiSynlig) {
                val erTele = tilstand == Tilstand.TELE_VENT || tilstand == Tilstand.TELE_LET
                visning?.invoke(g, if (erTele) listOf(teleFelt) else k.roier,
                    if (erTele) null else k.teleSone, sisteKlynge, status())
            }
        } catch (e: Exception) {
            Logg.skriv("feil i analysen: $e")
        } finally {
            bilde.close()
        }
    }

    private fun overvaak(g: Graa, naa: Long) {
        if (flagg.exists() && flagg.lastModified() != sistTitt) {
            sistTitt = flagg.lastModified()
            titt()
            return
        }
        if (naa < nattTil) return
        val lys = k.roier.map { g.lys(it) }.average()
        sisteLys = lys
        if (lys < k.lysMin) {
            if (!natt) Logg.skriv(String.format(Locale.ROOT, "moerkt (lys %.0f < %.0f), venter", lys, k.lysMin))
            natt = true
            nattTil = naa + 60_000
            forrige = null
            paaRad = 0
            return
        }
        if (natt) {
            natt = false
            Logg.skriv(String.format(Locale.ROOT, "lyst igjen (lys %.0f)", lys))
        }
        val f = forrige
        forrige = g
        if (f == null) return
        val m = bevegelse(f, g, k, k.roier)
        sisteMaal = m
        val klynge = m.klynge
        val treff = klynge != null && m.tette >= k.blokkerMin &&
            m.andel >= k.bevegelseAndel && m.andel <= k.bevegelseMaks
        paaRad = if (treff) paaRad + 1 else 0
        if (paaRad < k.varighet || klynge == null) return
        if (naa - sistHendelse < (k.pauseS * 1000).toLong()) return
        paaRad = 0
        hendelse(klynge, m, lys)
    }

    /** Bevegelse i klyngen: ta bildet, med telelinsen hvis den er ved materen. */
    private fun hendelse(klynge: Felt, m: Maal, lys: Double) {
        sisteKlynge = klynge
        val tele = k.tele && k.teleSone.inneholder(klynge.midtX, klynge.midtY)
        Logg.skriv(String.format(Locale.ROOT, "bevegelse %.2f %%, %d tette blokker ved (%.2f, %.2f)%s",
            m.andel * 100, m.tette, klynge.midtX, klynge.midtY, if (tele) ", ved materen" else ""))
        opptatt()
        taBilde { bilde ->
            if (bilde == null) {
                nullstill(pause = true)
                return@taBilde
            }
            val utsnitt = utsnittRundt(klynge, bilde.bredde, bilde.hoeyde, k)
            val jpeg = klipp(bilde.jpeg, bilde.grader, utsnitt).jpeg(k.jpegKvalitet)
            val meta = meta(m, lys, bilde, utsnitt, klynge)
            if (!tele) {
                sender.send(jpeg, meta, k)
                nullstill(pause = true)
                return@taBilde
            }
            reserve = Reserve(jpeg, meta)
            // Telelinsen ser midten av 1x-bildet forstoerret teleZoom ganger;
            // der leter den etter fuglen, i et felt rundt der den var.
            val cx = 0.5f + (klynge.midtX - 0.5f) * k.teleZoom
            val cy = 0.5f + (klynge.midtY - 0.5f) * k.teleZoom
            teleFelt = Felt((cx - 0.3f).coerceAtLeast(0f), (cy - 0.3f).coerceAtLeast(0f),
                (cx + 0.3f).coerceAtMost(1f), (cy + 0.3f).coerceAtMost(1f))
            zoom(k.teleZoom) {
                tilstand = Tilstand.TELE_VENT
                teleVentTil = SystemClock.elapsedRealtime() + k.teleVentMs
                forrige = null
            }
        }
    }

    private fun letTele(g: Graa, naa: Long) {
        val f = forrige
        forrige = g
        if (f != null) {
            val m = bevegelseI(f, g, k, teleFelt)
            val klynge = m.klynge
            if (klynge != null && m.tette >= k.blokkerMin && m.andel <= k.bevegelseMaks) {
                sisteKlynge = klynge
                Logg.skriv(String.format(Locale.ROOT, "telelinsen (%s): bevegelse ved (%.2f, %.2f), %d tette blokker",
                    aktivLinsenavn(), klynge.midtX, klynge.midtY, m.tette))
                opptatt()
                taBilde { bilde ->
                    if (bilde != null) {
                        val utsnitt = utsnittRundt(klynge, bilde.bredde, bilde.hoeyde, k)
                        val jpeg = klipp(bilde.jpeg, bilde.grader, utsnitt).jpeg(k.jpegKvalitet)
                        val meta = meta(m, sisteLys, bilde, utsnitt, klynge)
                        reserve = null
                        sender.send(jpeg, meta, k)
                    } else {
                        sendReserve("telebildet feilet")
                    }
                    nullstill(pause = true)
                }
                return
            }
        }
        if (naa > teleFrist) {
            opptatt()
            sendReserve(String.format(Locale.ROOT, "ingen bevegelse med telelinsen paa %.1f s", k.teleLetingS))
            nullstill(pause = true)
        }
    }

    private fun sendReserve(grunn: String) {
        val r = reserve ?: return
        reserve = null
        Logg.skriv("$grunn; sender 1x-bildet")
        sender.send(r.jpeg, r.meta.put("reserve", grunn), k)
    }

    private fun opptatt() {
        tilstand = Tilstand.OPPTATT
        opptattSiden = SystemClock.elapsedRealtime()
    }

    /** Tilbake til overvaaking paa 1x. Med pause venter neste bilde pause_s. */
    private fun nullstill(pause: Boolean) {
        if (pause) sistHendelse = SystemClock.elapsedRealtime()
        forrige = null
        paaRad = 0
        reserve = null
        val z = kamera?.cameraInfo?.zoomState?.value?.zoomRatio ?: 1f
        if (z == 1f) {
            tilstand = Tilstand.OVERVAAK
            return
        }
        opptatt()
        zoom(1f) {
            traad.schedule(Runnable {
                forrige = null
                tilstand = Tilstand.OVERVAAK
            }, k.teleVentMs, TimeUnit.MILLISECONDS)
        }
    }

    private fun zoom(z: Float, deretter: () -> Unit) {
        val kam = kamera ?: return deretter()
        kam.cameraControl.setZoomRatio(z).addListener({ deretter() }, traad)
    }

    /**
     * Helt bilde med feltene tegnet inn, til aa sikte og sette feltene fra
     * Macen. Med "test x y" i flagget i stedet: en tenkt bevegelse i punktet,
     * som kjoerer hele veien med utsnitt, telelinse og reserve (kjor.sh test).
     */
    private fun titt() {
        val innhold = runCatching { flagg.readText().trim() }.getOrDefault("")
        runCatching { flagg.delete() }
        val ord = innhold.split(Regex("\\s+"))
        if (ord.size == 3 && ord[0] == "test") {
            val x = ord[1].toFloat()
            val y = ord[2].toFloat()
            val klynge = Felt(x - 0.01f, y - 0.01f, x + 0.01f, y + 0.01f)
            Logg.skriv("testhendelse")
            return hendelse(klynge, Maal(0.0, 0, klynge), sisteLys)
        }
        val tele = innhold == "tele"
        opptatt()
        val ta = {
            taBilde { bilde ->
                if (bilde != null) {
                    try {
                        val bm = klipp(bilde.jpeg, bilde.grader, Felt.HELE, nedskaler = 2)
                        val tegnet = if (tele) bm else tegnFelter(bm, k.roier, k.teleSone, sisteKlynge)
                        val tmp = File(mappe, "siste.jpg.tmp")
                        tmp.writeBytes(tegnet.jpeg(90))
                        tmp.renameTo(File(mappe, "siste.jpg"))
                        Logg.skriv("tok bilde av hele rammen${if (tele) " med telelinsen" else ""} -> siste.jpg")
                    } catch (e: Exception) {
                        Logg.skriv("titt feilet: $e")
                    }
                }
                nullstill(pause = false)
            }
        }
        if (tele) zoom(k.teleZoom) { traad.schedule(Runnable { ta() }, k.teleVentMs, TimeUnit.MILLISECONDS) }
        else ta()
    }

    // ------------------------------------------------------------------
    // Bildet
    // ------------------------------------------------------------------

    /**
     * Et bilde i full opploesning. Er autoeksponeringen tregere enn
     * lukker_maks_s, settes lukker og ISO for hånd saa lyset blir det samme,
     * og tilbake til auto etterpaa.
     */
    private fun taBilde(ferdig: (Tatt?) -> Unit) {
        val kam = kamera
        val taker = bildetaker
        if (kam == null || taker == null) return ferdig(null)
        val plan = raskLukker()
        val kontroll = Camera2CameraControl.from(kam.cameraControl)
        val ta = Runnable {
            taker.takePicture(traad, object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(bilde: ImageProxy) {
                    val tatt = try {
                        val buf = bilde.planes[0].buffer
                        val jpeg = ByteArray(buf.remaining()).also { buf.get(it) }
                        val grader = (bilde.imageInfo.rotationDegrees + k.roter) % 360
                        val staar = grader % 180 == 0
                        Tatt(jpeg, grader,
                            if (staar) bilde.width else bilde.height,
                            if (staar) bilde.height else bilde.width,
                            plan?.first ?: aeTidNs, plan?.second ?: aeIso, plan != null,
                            aktivLinse, aktivLinsenavn(), kam.cameraInfo.zoomState.value?.zoomRatio ?: 1f)
                    } finally {
                        bilde.close()
                    }
                    if (plan != null) kontroll.setCaptureRequestOptions(grunnvalg().build())
                    ferdig(tatt)
                }

                override fun onError(exception: ImageCaptureException) {
                    Logg.skriv("bildet feilet: ${exception.message}")
                    if (plan != null) kontroll.setCaptureRequestOptions(grunnvalg().build())
                    ferdig(null)
                }
            })
        }
        if (plan == null) return ta.run()
        val valg = grunnvalg()
            .setCaptureRequestOption(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_OFF)
            .setCaptureRequestOption(CaptureRequest.SENSOR_EXPOSURE_TIME, plan.first)
            .setCaptureRequestOption(CaptureRequest.SENSOR_SENSITIVITY, plan.second)
        if (boostOmraade != null) valg.setCaptureRequestOption(CaptureRequest.CONTROL_POST_RAW_SENSITIVITY_BOOST, 100)
        // Et par rammer til de nye verdiene er i sensoren.
        kontroll.setCaptureRequestOptions(valg.build())
            .addListener({ traad.schedule(ta, 150, TimeUnit.MILLISECONDS) }, traad)
    }

    /** (lukkertid ns, ISO) med samme lys som autoeksponeringen, eller null naar den er rask nok. */
    private fun raskLukker(): Pair<Long, Int>? {
        if (k.lukkerMaksS <= 0) return null
        val t = aeTidNs ?: return null
        val iso = aeIso ?: return null
        val maal = (k.lukkerMaksS * 1e9).toLong()
        if (t <= maal) return null
        val effektiv = iso * (aeBoost ?: 100) / 100.0
        val tak = min(k.isoMaks, isoOmraade?.upper ?: k.isoMaks)
        var nyT = maal
        var nyIso = effektiv * t / maal
        if (nyIso > tak) {
            nyT = (maal * nyIso / tak).toLong()
            nyIso = tak.toDouble()
        }
        if (nyT >= t) return null
        return nyT to nyIso.roundToInt().coerceIn(isoOmraade?.lower ?: 50, tak)
    }

    private fun meta(m: Maal, lys: Double, b: Tatt, utsnitt: Felt, klynge: Felt): JSONObject {
        fun avrund(v: Double, d: Int) = Math.round(v * Math.pow(10.0, d.toDouble())) / Math.pow(10.0, d.toDouble())
        return JSONObject().apply {
            put("host", Build.MODEL)
            put("bevegelse", avrund(m.andel, 4))
            put("tette", m.tette)
            put("lys", avrund(lys, 1))
            put("linse", b.linse)
            put("fysisk", b.fysisk ?: JSONObject.NULL)
            put("zoom", avrund(b.zoom.toDouble(), 2))
            b.tidNs?.let { put("eksponering_us", it / 1000) }
            b.iso?.let { put("iso", it) }
            put("rask_lukker", b.rask)
            fokus?.let { if (it.isFinite()) put("fokus", avrund(it.toDouble(), 2)) }
            put("utsnitt", utsnitt.json())
            put("klynge", klynge.json())
            put("roi", JSONArray(k.roier.map { it.json() }))
            aktivitet.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED), Context.RECEIVER_NOT_EXPORTED)?.let {
                put("temp_c", it.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0)
                val nivaa = it.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                if (nivaa >= 0) put("batteri", 100 * nivaa / it.getIntExtra(BatteryManager.EXTRA_SCALE, 100))
                put("lader", it.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0)
            }
            put("varme", aktivitet.getSystemService(PowerManager::class.java).currentThermalStatus)
        }
    }

    // ------------------------------------------------------------------
    // Konfig og status
    // ------------------------------------------------------------------

    private fun lesKonfig(): Konfig = try {
        Konfig.les(konfigFil)
    } catch (e: Exception) {
        Logg.skriv("kamera.json er ugyldig ($e); beholder innstillingene")
        k
    }

    private fun sjekkKonfig() {
        val t = konfigFil.lastModified()
        if (t == konfigTid) return
        konfigTid = t
        val gammel = k
        k = lesKonfig()
        if (k.analyseBredde != gammel.analyseBredde || k.fps != gammel.fps) {
            Logg.skriv("analyse_bredde og fps gjelder foerst ved neste start")
        }
        if (k.fokusM != gammel.fokusM) settGrunnvalg()
        Logg.skriv("konfig lest paa nytt: send ${if (k.send) "paa" else "av"}, felt ${k.roier.map { it.json() }}, " +
            "tele ${if (k.tele) "i ${k.teleSone.json()}" else "av"}")
    }

    private fun status(): String {
        val z = kamera?.cameraInfo?.zoomState?.value?.zoomRatio ?: 1f
        return buildString {
            appendLine(String.format(Locale.ROOT, "%s  zoom %.1fx (%s)  lys %.0f%s",
                tilstand.name.lowercase(), z, aktivLinsenavn(), sisteLys, if (natt) "  natt" else ""))
            appendLine(String.format(Locale.ROOT, "bevegelse %.2f %%  tette blokker %d  paa rad %d",
                sisteMaal.andel * 100, sisteMaal.tette, paaRad))
            appendLine("send ${if (k.send) "paa" else "av"}: ${sender.sendt} sendt, " +
                "${sender.lagret} bare lagret, ${sender.feilet} feilet")
            aeTidNs?.let {
                appendLine(String.format(Locale.ROOT, "autoeksponering 1/%.0f s, ISO %d", 1e9 / it, aeIso ?: 0))
            }
            Logg.sisteLinjer().forEach { appendLine(it) }
        }.trimEnd()
    }
}
