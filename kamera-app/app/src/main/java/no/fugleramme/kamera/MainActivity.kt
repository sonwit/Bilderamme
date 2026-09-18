package no.fugleramme.kamera

/*
 * Fuglekameraet paa Pixel-en. Skjermen er svart mens telefonen henger i
 * vinduet -- ikke noe lys eller bevegelse. Dobbelttrykk viser det kameraet
 * ser (graatonebildet bevegelsen maales i, med feltene tegnet inn) og status;
 * dobbelttrykk igjen, eller ti minutter, skjuler det. Selve arbeidet gjoer
 * Fuglekamera.
 *
 * Skjermen staar paa hele tiden, bare svart: kameraet faar bare brukes av en
 * app som er framme. Velges appen som startskjerm, starter den ogsaa av seg
 * selv etter en omstart.
 *
 * Akselerometeret sier hvilken vei telefonen henger, og bildene snus etter
 * det -- ogsaa naar auto-rotering er av. Aktiviteten staar fast i landskap,
 * saa visningen dreies for haand til den staar riktig for den som ser paa.
 */

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.OrientationEventListener
import android.view.Surface
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import kotlin.math.abs
import kotlin.math.min

class MainActivity : ComponentActivity() {

    private lateinit var fuglekamera: Fuglekamera
    private lateinit var gui: FrameLayout
    private lateinit var bilde: ImageView
    private lateinit var tekst: TextView
    private val handler = Handler(Looper.getMainLooper())
    private val skjul = Runnable { visGui(false) }
    private lateinit var retning: OrientationEventListener
    private var rotasjon = Surface.ROTATION_90

    private val tillatelse =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
            if (ok) fuglekamera.start() else Logg.skriv("fikk ikke lov til aa bruke kameraet")
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.setBackgroundDrawable(ColorDrawable(Color.BLACK))
        window.attributes = window.attributes.apply {
            layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
        }
        val mappe = getExternalFilesDir(null) ?: filesDir
        Logg.init(mappe)
        byggSkjerm()
        fuglekamera = Fuglekamera(this, mappe)
        fuglekamera.visning = { g, felter, teleSone, klynge, status ->
            val bm = tegnFelter(g.bitmap(2), felter, teleSone, klynge)
            runOnUiThread {
                bilde.setImageBitmap(bm)
                tekst.text = status
            }
        }
        retning = object : OrientationEventListener(this) {
            override fun onOrientationChanged(vinkel: Int) {
                if (vinkel == ORIENTATION_UNKNOWN) return
                val naermest = (vinkel + 45) / 90 % 4 * 90
                // Bare naer en av de fire retningene, saa den ikke vipper
                // fram og tilbake rundt 45 grader.
                val avvik = abs(vinkel - naermest).let { min(it, 360 - it) }
                if (avvik > 30) return
                val r = when (naermest) {
                    0 -> Surface.ROTATION_0
                    90 -> Surface.ROTATION_270
                    180 -> Surface.ROTATION_180
                    else -> Surface.ROTATION_90
                }
                if (r == rotasjon) return
                rotasjon = r
                fuglekamera.settRotasjon(r)
                snuGui()
            }
        }
        if (retning.canDetectOrientation()) retning.enable()
        visGui(false)
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            fuglekamera.start()
        } else {
            tillatelse.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onDestroy() {
        retning.disable()
        super.onDestroy()
    }

    /** Dreier visningen saa den staar riktig vei slik telefonen henger. */
    private fun snuGui() {
        val rot = gui.parent as View
        if (rot.width == 0 || rot.height == 0) {
            rot.post { snuGui() }
            return
        }
        val grader = when (rotasjon) {
            Surface.ROTATION_0 -> 0
            Surface.ROTATION_90 -> 90
            Surface.ROTATION_180 -> 180
            else -> 270
        }
        // Aktiviteten staar i landskap (90); forskjellen er det visningen maa dreies.
        val vri = ((grader - 90) % 360 + 360) % 360
        val lp = gui.layoutParams as FrameLayout.LayoutParams
        if (vri % 180 == 0) {
            lp.width = rot.width; lp.height = rot.height
        } else {
            lp.width = rot.height; lp.height = rot.width
        }
        lp.gravity = Gravity.CENTER
        gui.layoutParams = lp
        gui.rotation = vri.toFloat()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            window.insetsController?.let {
                it.hide(WindowInsets.Type.systemBars())
                it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        }
    }

    private fun byggSkjerm() {
        val rot = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        gui = FrameLayout(this)
        bilde = ImageView(this).apply { scaleType = ImageView.ScaleType.FIT_CENTER }
        tekst = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(0x99000000.toInt())
            typeface = Typeface.MONOSPACE
            textSize = 11f
            setPadding(24, 16, 24, 16)
        }
        gui.addView(bilde, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        gui.addView(tekst, FrameLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.BOTTOM or Gravity.START))
        rot.addView(gui, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        val dobbelttrykk = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent) = true
            override fun onDoubleTap(e: MotionEvent): Boolean {
                visGui(gui.visibility != View.VISIBLE)
                return true
            }
        })
        rot.setOnTouchListener { v, e ->
            dobbelttrykk.onTouchEvent(e)
            if (e.action == MotionEvent.ACTION_UP) v.performClick()
            true
        }
        setContentView(rot)
    }

    private fun visGui(vis: Boolean) {
        gui.visibility = if (vis) View.VISIBLE else View.GONE
        fuglekamera.guiSynlig = vis
        window.attributes = window.attributes.apply {
            screenBrightness = if (vis) WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE else 0f
        }
        handler.removeCallbacks(skjul)
        if (vis) {
            handler.postDelayed(skjul, 10 * 60_000L)
        } else {
            bilde.setImageDrawable(null)
            tekst.text = ""
        }
    }
}
