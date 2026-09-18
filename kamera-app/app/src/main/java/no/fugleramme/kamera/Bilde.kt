package no.fugleramme.kamera

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapRegionDecoder
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Rect
import java.io.ByteArrayOutputStream
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Feltet i sensorens retning, naar sensorbildet maa roteres [grader] med
 * klokka for aa staa slik feltet er gitt.
 */
fun Felt.tilSensor(grader: Int): Felt = when (grader) {
    90 -> Felt(y0, 1 - x1, y1, 1 - x0)
    180 -> Felt(1 - x1, 1 - y1, 1 - x0, 1 - y0)
    270 -> Felt(1 - y1, x0, 1 - y0, x1)
    else -> this
}

/**
 * Kvadratisk utsnitt rundt klyngen, som andeler av et bilde paa w x h
 * piksler (slik det staar). Sida er minst utsnitt_min_px og ellers klyngen
 * ganger utsnitt_faktor, saa en stor fugl ikke blir kuttet.
 */
fun utsnittRundt(klynge: Felt, w: Int, h: Int, k: Konfig): Felt {
    val side = max(k.utsnittMinPx.toDouble(),
        k.utsnittFaktor * max(klynge.bredde.toDouble() * w, klynge.hoeyde.toDouble() * h))
        .coerceAtMost(min(w, h).toDouble())
    val x0 = (klynge.midtX.toDouble() * w - side / 2).coerceIn(0.0, w - side)
    val y0 = (klynge.midtY.toDouble() * h - side / 2).coerceIn(0.0, h - side)
    return Felt((x0 / w).toFloat(), (y0 / h).toFloat(),
        ((x0 + side) / w).toFloat(), ((y0 + side) / h).toFloat())
}

/**
 * Feltet (i bildet slik det staar) klippet ut av en JPEG i sensorens retning
 * og rotert [grader] med klokka. Bare feltet dekodes, saa 12 MP-bildet aldri
 * ligger helt i minnet.
 */
fun klipp(jpeg: ByteArray, grader: Int, felt: Felt, nedskaler: Int = 1): Bitmap {
    val dekoder = BitmapRegionDecoder.newInstance(jpeg, 0, jpeg.size)
    try {
        val w = dekoder.width
        val h = dekoder.height
        val s = felt.tilSensor(grader)
        val r = Rect(
            (s.x0 * w).roundToInt().coerceIn(0, w - 1), (s.y0 * h).roundToInt().coerceIn(0, h - 1),
            (s.x1 * w).roundToInt().coerceIn(1, w), (s.y1 * h).roundToInt().coerceIn(1, h))
        val bm = dekoder.decodeRegion(r, BitmapFactory.Options().apply { inSampleSize = nedskaler })
        if (grader == 0) return bm
        val m = Matrix().apply { postRotate(grader.toFloat()) }
        val snudd = Bitmap.createBitmap(bm, 0, 0, bm.width, bm.height, m, true)
        if (snudd !== bm) bm.recycle()
        return snudd
    } finally {
        dekoder.recycle()
    }
}

fun Bitmap.jpeg(kvalitet: Int): ByteArray =
    ByteArrayOutputStream().also { compress(Bitmap.CompressFormat.JPEG, kvalitet, it) }.toByteArray()

/** Graatonebildet som bitmap til skjermen, hver [hver] piksel. */
fun Graa.bitmap(hver: Int): Bitmap {
    val bw = w / hver
    val bh = h / hver
    val farger = IntArray(bw * bh)
    for (y in 0 until bh) {
        val rad = y * hver * w
        for (x in 0 until bw) {
            val v = px[rad + x * hver].toInt() and 0xFF
            farger[y * bw + x] = (0xFF shl 24) or (v shl 16) or (v shl 8) or v
        }
    }
    return Bitmap.createBitmap(bw, bh, Bitmap.Config.ARGB_8888).apply { setPixels(farger, 0, bw, 0, 0, bw, bh) }
}

/** Feltene tegnet inn: overvaakingsfeltene groenne, telesona roed og siste klynge gul. */
fun tegnFelter(bm: Bitmap, felter: List<Felt>, teleSone: Felt?, klynge: Felt?): Bitmap {
    val ut = if (bm.isMutable) bm else bm.copy(Bitmap.Config.ARGB_8888, true)
    val lerret = Canvas(ut)
    val strek = max(2f, ut.width / 400f)
    fun tegn(f: Felt, farge: Int) {
        val p = Paint().apply { color = farge; style = Paint.Style.STROKE; strokeWidth = strek }
        lerret.drawRect(f.x0 * ut.width, f.y0 * ut.height, f.x1 * ut.width, f.y1 * ut.height, p)
    }
    felter.forEach { tegn(it, Color.GREEN) }
    teleSone?.let { tegn(it, Color.RED) }
    klynge?.let { tegn(it, Color.YELLOW) }
    return ut
}
