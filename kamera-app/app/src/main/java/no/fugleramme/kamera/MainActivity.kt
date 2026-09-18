package no.fugleramme.kamera

/*
 * Kameratest for Pixel-en -- foerste steg mot fuglekameraet som app.
 *
 * Svarer paa ett spoersmaal foer resten bygges: faar en vanlig app bruke
 * telelinsen (5x) paa Pixel 9 Pro? Materen staar 8-10 m unna, og med
 * telelinsen blir en meis rundt 100 px i 1080p mot 25 px for et vanlig
 * webkamera. Appen
 *
 *   1. skriver ut kameraene telefonen viser fram til apper, med brennvidde,
 *      bildevinkel og opploesning -- ogsaa de fysiske linsene bak det
 *      logiske bakkameraet,
 *   2. tar tre bilder med bakkameraet, zoom 1x, 5x og 10x, og noterer hvilken
 *      fysisk linse telefonen faktisk brukte til hvert av dem.
 *
 * Bildene og rapporten (kameratest.txt) havner i appens mappe paa telefonen og
 * hentes med kjor.sh hent. Ingenting sendes til serveren: testbilder skal ikke
 * til Gemini eller inn i fuglestatistikken.
 */

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.ImageFormat
import android.graphics.Typeface
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import java.io.File
import java.util.Locale
import kotlin.math.atan
import kotlin.math.hypot

private const val TAG = "Fuglekamera"

// Zoomnivaaene som testes. Pixel-appen bytter til telelinsen ved 5x.
private val ZOOM = listOf(1f, 5f, 10f)

// Hvor lenge kameraet faar etter et zoombytte foer bildet tas: linsebytte,
// fokus og eksponering.
private const val VENT_MS = 3000L

class MainActivity : ComponentActivity() {

    private lateinit var forhaandsvisning: PreviewView
    private lateinit var knapp: Button
    private lateinit var tekst: TextView

    private var kamera: Camera? = null
    private var bildetaker: ImageCapture? = null

    // Den fysiske linsen bak det logiske kameraet i siste ferdige ramme.
    @Volatile private var aktivLinse: String? = null

    private val logg = StringBuilder()
    private val handler = Handler(Looper.getMainLooper())

    private val tillatelse =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
            if (ok) startKamera() else skriv("fikk ikke lov til aa bruke kameraet")
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        byggSkjerm()
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startKamera()
        } else {
            tillatelse.launch(Manifest.permission.CAMERA)
        }
    }

    private fun byggSkjerm() {
        val rot = FrameLayout(this)
        forhaandsvisning = PreviewView(this)
        rot.addView(forhaandsvisning, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xB0000000.toInt())
            fitsSystemWindows = true
        }
        knapp = Button(this).apply {
            text = "Ta bildene paa nytt"
            isEnabled = false
            setOnClickListener { taSerie() }
        }
        tekst = TextView(this).apply {
            setTextColor(Color.WHITE)
            typeface = Typeface.MONOSPACE
            textSize = 10f
            setPadding(16, 8, 16, 8)
        }
        panel.addView(knapp)
        panel.addView(ScrollView(this).apply { addView(tekst) },
            LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f))
        rot.addView(panel, FrameLayout.LayoutParams(
            MATCH_PARENT, resources.displayMetrics.heightPixels / 2, Gravity.BOTTOM))
        setContentView(rot)
    }

    @OptIn(markerClass = [ExperimentalCamera2Interop::class])
    private fun startKamera() {
        skriv(beskrivKameraer())
        val fremtid = ProcessCameraProvider.getInstance(this)
        fremtid.addListener({
            val leverandoer = fremtid.get()
            val pb = Preview.Builder()
            // Hver ferdige ramme sier hvilken fysisk linse den kom fra. Det er
            // fasiten paa om zoom 5x faktisk gir telelinsen.
            Camera2Interop.Extender(pb).setSessionCaptureCallback(
                object : CameraCaptureSession.CaptureCallback() {
                    override fun onCaptureCompleted(
                        session: CameraCaptureSession,
                        request: CaptureRequest,
                        result: TotalCaptureResult,
                    ) {
                        aktivLinse = result.get(CaptureResult.LOGICAL_MULTI_CAMERA_ACTIVE_PHYSICAL_ID)
                    }
                })
            val forhaand = pb.build()
            forhaand.setSurfaceProvider(forhaandsvisning.surfaceProvider)
            val taker = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                .build()
            leverandoer.unbindAll()
            kamera = leverandoer.bindToLifecycle(
                this, CameraSelector.DEFAULT_BACK_CAMERA, forhaand, taker)
            bildetaker = taker
            handler.postDelayed({ taSerie() }, VENT_MS)
        }, mainExecutor)
    }

    private fun beskrivKameraer(): String {
        val cm = getSystemService(CameraManager::class.java)
        val kanAapnes = cm.cameraIdList.toSet()
        val sb = StringBuilder()
        sb.appendLine("${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} " +
            "(API ${Build.VERSION.SDK_INT})")
        for (id in cm.cameraIdList) {
            val ch = cm.getCameraCharacteristics(id)
            sb.appendLine("kamera $id: ${beskriv(ch)}")
            for (p in ch.physicalCameraIds.sorted()) {
                val merk = if (p in kanAapnes) ", kan aapnes direkte" else ""
                sb.appendLine("  fysisk $p: ${beskriv(cm.getCameraCharacteristics(p))}$merk")
            }
        }
        return sb.toString().trimEnd()
    }

    private fun beskriv(ch: CameraCharacteristics): String {
        val deler = mutableListOf<String>()
        deler += when (ch.get(CameraCharacteristics.LENS_FACING)) {
            CameraCharacteristics.LENS_FACING_BACK -> "bak"
            CameraCharacteristics.LENS_FACING_FRONT -> "front"
            else -> "ekstern"
        }
        val evner = ch.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES) ?: IntArray(0)
        if (CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES_LOGICAL_MULTI_CAMERA in evner) {
            deler += "logisk"
        }
        val f = ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)?.firstOrNull()
        val sensor = ch.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
        if (f != null && sensor != null) {
            // 43,27 mm er diagonalen i et 35 mm-bilde.
            val ekv = f * 43.27f / hypot(sensor.width, sensor.height)
            val vinkel = Math.toDegrees(2 * atan(sensor.width / (2.0 * f)))
            deler += String.format(Locale.ROOT,
                "f %.2f mm (ca. %.0f mm ekv.), %.0f grader vannrett", f, ekv, vinkel)
        }
        ch.get(CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)?.let {
            deler += "sensor ${it.width}x${it.height}"
        }
        ch.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
            ?.getOutputSizes(ImageFormat.JPEG)
            ?.maxByOrNull { it.width.toLong() * it.height }
            ?.let { deler += "JPEG ${it.width}x${it.height}" }
        ch.get(CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE)?.let {
            deler += String.format(Locale.ROOT, "zoom %.1f-%.1fx", it.lower, it.upper)
        }
        ch.get(CameraCharacteristics.LENS_INFO_MINIMUM_FOCUS_DISTANCE)?.let {
            if (it > 0f) deler += String.format(Locale.ROOT, "naermeste fokus %.0f cm", 100f / it)
        }
        return deler.joinToString(", ")
    }

    private fun taSerie() {
        if (kamera == null || bildetaker == null) return
        knapp.isEnabled = false
        skriv("--- bilder ---")
        taBilde(0)
    }

    private fun taBilde(i: Int) {
        if (i >= ZOOM.size) {
            skriv("ferdig")
            knapp.isEnabled = true
            return
        }
        val z = ZOOM[i]
        val k = kamera ?: return
        k.cameraControl.setZoomRatio(z)
        handler.postDelayed({
            val linse = aktivLinse
            val fikk = k.cameraInfo.zoomState.value?.zoomRatio ?: Float.NaN
            val navn = String.format(Locale.ROOT, "zoom_%02.0fx.jpg", z)
            val fil = File(getExternalFilesDir(null), navn)
            val valg = ImageCapture.OutputFileOptions.Builder(fil).build()
            bildetaker!!.takePicture(valg, mainExecutor, object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(resultat: ImageCapture.OutputFileResults) {
                    skriv(String.format(Locale.ROOT, "zoom %.0fx (fikk %.1fx): linse %s, %s, %d kB",
                        z, fikk, linse ?: "ukjent", navn, fil.length() / 1024))
                    taBilde(i + 1)
                }

                override fun onError(feil: ImageCaptureException) {
                    skriv("zoom ${z}x: feil: ${feil.message}")
                    taBilde(i + 1)
                }
            })
        }, VENT_MS)
    }

    private fun skriv(s: String) {
        Log.i(TAG, s)
        logg.appendLine(s)
        tekst.text = logg
        File(getExternalFilesDir(null), "kameratest.txt").writeText(logg.toString())
    }
}
