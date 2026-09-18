package no.fugleramme.kamera

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Et felt i bildet som andeler av bredde og hoeyde, i bildet slik det staar (etter rotasjon). */
data class Felt(val x0: Float, val y0: Float, val x1: Float, val y1: Float) {
    val bredde get() = x1 - x0
    val hoeyde get() = y1 - y0
    val midtX get() = (x0 + x1) / 2
    val midtY get() = (y0 + y1) / 2

    fun inneholder(x: Float, y: Float) = x in x0..x1 && y in y0..y1

    fun json() = JSONArray(listOf(x0, y0, x1, y1).map { Math.round(it * 1000) / 1000.0 })

    companion object {
        val HELE = Felt(0f, 0f, 1f, 1f)

        fun fra(a: JSONArray) = Felt(
            a.getDouble(0).toFloat(), a.getDouble(1).toFloat(),
            a.getDouble(2).toFloat(), a.getDouble(3).toFloat())
    }
}

/**
 * Innstillingene. Leses fra kamera.json i appens mappe paa telefonen (kjor.sh
 * konfig legger den der) og leses paa nytt naar fila endres. Navnene er de
 * samme som i kamera/kamera.py der de betyr det samme; se kommentarene der for
 * hvorfor bevegelsestersklene er som de er.
 */
data class Konfig(
    val server: String = "http://192.168.1.38:8091",
    val token: String = "",
    // Av: bildene lagres bare paa telefonen (kjor.sh bilder henter dem).
    val send: Boolean = false,
    // Feltene bevegelse maales i, som andeler av 1x-bildet slik det staar.
    val roier: List<Felt> = listOf(Felt.HELE),
    val varighet: Int = 2,
    val diffTerskel: Int = 28,
    // Tersklene er andeler av feltet. kamera.py hadde smaa felt rundt hver
    // mater; her er feltet hele hagen, og en spettmeis ved materen er rundt
    // 20x10 px av 1280x960 paa 1x -- noen hundre endrede piksler, 0,02 %.
    val bevegelseAndel: Double = 0.0001,
    val bevegelseMaks: Double = 0.08,
    val blokk: Int = 4,
    val blokkAndel: Double = 0.5,
    val blokkerMin: Int = 3,
    val klyngeMaks: Double = 0.03,
    val pauseS: Double = 60.0,
    val rammeS: Double = 0.5,
    val lysMin: Double = 25.0,
    // Appen snur bildet selv etter hvilken vei telefonen henger. Dette er
    // bare en ekstra rotasjon oppaa, 0/90/180/270 grader med klokka, hvis
    // den tar feil. Feltene gjelder bildet slik det staar.
    val roter: Int = 0,
    val analyseBredde: Int = 1280,
    // Bilderaten kameraet kjoerer i. 15 i stedet for 30 halverer arbeidet
    // telefonen gjoer hele dagen; 0 = kameraets eget valg.
    val fps: Int = 15,
    val jpegKvalitet: Int = 90,
    // Utsnittet rundt fuglen: minst saa mange piksler i sida, og ellers
    // klyngen ganger faktoren. Serveren krymper til 768 px.
    val utsnittMinPx: Int = 768,
    val utsnittFaktor: Double = 2.5,
    // Bevegelse med midtpunkt i tele_sone tas med telelinsen. Telelinsen ser
    // midtre femtedel av 1x-bildet (zoom 5x); sona ligger litt innenfor.
    val tele: Boolean = true,
    val teleZoom: Float = 5f,
    val teleSone: Felt = Felt(0.41f, 0.41f, 0.59f, 0.59f),
    val teleVentMs: Long = 1000,
    val teleLetingS: Double = 2.5,
    // Lengste lukkertid for bildene som sendes. Autoeksponeringen valgte
    // 1/30 s med telelinsen i dagslys 18. sep 2026 -- for sakte for fugler.
    // 0 = la kameraet velge.
    val lukkerMaksS: Double = 0.003,
    val isoMaks: Int = 1600,
    // Fast fokusavstand i meter. 0 = autofokus.
    val fokusM: Double = 0.0,
) {
    companion object {
        fun les(fil: File): Konfig {
            val s = Konfig()
            if (!fil.exists()) return s
            val j = JSONObject(fil.readText())
            fun d(n: String, v: Double) = j.optDouble(n, v)
            fun i(n: String, v: Int) = j.optInt(n, v)
            val roier = j.optJSONArray("roier")
                ?.let { a -> (0 until a.length()).map { Felt.fra(a.getJSONArray(it)) } }
                .orEmpty()
                .ifEmpty { j.optJSONArray("roi")?.let { listOf(Felt.fra(it)) } ?: s.roier }
            return Konfig(
                server = j.optString("server", s.server).trimEnd('/'),
                token = j.optString("token", s.token),
                send = j.optBoolean("send", s.send),
                roier = roier,
                varighet = i("varighet", s.varighet),
                diffTerskel = i("diff_terskel", s.diffTerskel),
                bevegelseAndel = d("bevegelse_andel", s.bevegelseAndel),
                bevegelseMaks = d("bevegelse_maks", s.bevegelseMaks),
                blokk = i("blokk", s.blokk),
                blokkAndel = d("blokk_andel", s.blokkAndel),
                blokkerMin = i("blokker_min", s.blokkerMin),
                klyngeMaks = d("klynge_maks", s.klyngeMaks),
                pauseS = d("pause_s", s.pauseS),
                rammeS = d("ramme_s", s.rammeS),
                lysMin = d("lys_min", s.lysMin),
                roter = ((i("roter", s.roter) % 360) + 360) % 360,
                analyseBredde = i("analyse_bredde", s.analyseBredde),
                fps = i("fps", s.fps),
                jpegKvalitet = i("jpeg_kvalitet", s.jpegKvalitet),
                utsnittMinPx = i("utsnitt_min_px", s.utsnittMinPx),
                utsnittFaktor = d("utsnitt_faktor", s.utsnittFaktor),
                tele = j.optBoolean("tele", s.tele),
                teleZoom = d("tele_zoom", s.teleZoom.toDouble()).toFloat(),
                teleSone = j.optJSONArray("tele_sone")?.let { Felt.fra(it) } ?: s.teleSone,
                teleVentMs = j.optLong("tele_vent_ms", s.teleVentMs),
                teleLetingS = d("tele_leting_s", s.teleLetingS),
                lukkerMaksS = d("lukker_maks_s", s.lukkerMaksS),
                isoMaks = i("iso_maks", s.isoMaks),
                fokusM = d("fokus_m", s.fokusM),
            )
        }
    }
}
