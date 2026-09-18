package no.fugleramme.kamera

import androidx.camera.core.ImageProxy
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Et graatonebilde, rad for rad, slik det staar (etter rotasjon). */
class Graa(val w: Int, val h: Int, val px: ByteArray) {

    /** Gjennomsnittlig lysstyrke (0-255) i feltet, hver annen piksel. */
    fun lys(felt: Felt): Double {
        val x0 = (felt.x0 * w).toInt().coerceIn(0, w)
        val x1 = (felt.x1 * w).toInt().coerceIn(0, w)
        val y0 = (felt.y0 * h).toInt().coerceIn(0, h)
        val y1 = (felt.y1 * h).toInt().coerceIn(0, h)
        var sum = 0L
        var n = 0
        for (y in y0 until y1 step 2) {
            val rad = y * w
            for (x in x0 until x1 step 2) {
                sum += px[rad + x].toInt() and 0xFF
                n++
            }
        }
        return if (n == 0) 0.0 else sum.toDouble() / n
    }

    /** Rotert 0, 90, 180 eller 270 grader med klokka. */
    fun rotert(grader: Int): Graa = when (grader) {
        90 -> {
            val ut = ByteArray(px.size)
            for (y in 0 until h) {
                val rad = y * w
                val u = h - 1 - y
                for (x in 0 until w) ut[x * h + u] = px[rad + x]
            }
            Graa(h, w, ut)
        }
        180 -> {
            val ut = ByteArray(px.size)
            val n = px.size - 1
            for (i in px.indices) ut[n - i] = px[i]
            Graa(w, h, ut)
        }
        270 -> {
            val ut = ByteArray(px.size)
            for (y in 0 until h) {
                val rad = y * w
                for (x in 0 until w) ut[(w - 1 - x) * h + y] = px[rad + x]
            }
            Graa(h, w, ut)
        }
        else -> this
    }
}

/** Y-planet (lysstyrken) fra en YUV-ramme, rotert slik bildet staar. */
fun graaFra(bilde: ImageProxy, grader: Int): Graa {
    val plan = bilde.planes[0]
    val buf = plan.buffer
    val w = bilde.width
    val h = bilde.height
    val px = ByteArray(w * h)
    if (plan.pixelStride == 1) {
        for (y in 0 until h) {
            buf.position(y * plan.rowStride)
            buf.get(px, y * w, w)
        }
    } else {
        for (y in 0 until h) for (x in 0 until w) {
            px[y * w + x] = buf.get(y * plan.rowStride + x * plan.pixelStride)
        }
    }
    return Graa(w, h, px).rotert(grader)
}

/** Maalet for to rammer: andel endrede piksler, antall tette blokker og klyngen de ligger i. */
data class Maal(val andel: Double, val tette: Int, val klynge: Felt?)

/** Stoerste maal over feltene, som bevegelse() i kamera.py. */
fun bevegelse(forrige: Graa, naa: Graa, k: Konfig, felter: List<Felt>): Maal {
    var beste = Maal(0.0, 0, null)
    for (f in felter) {
        val m = bevegelseI(forrige, naa, k, f)
        if (m.tette > beste.tette || (m.tette == beste.tette && m.andel > beste.andel)) beste = m
    }
    return beste
}

/**
 * Samme maal som _bevegelse_i() i kamera.py: andelen alene skiller ikke fugl
 * fra vind, saa feltet deles i blokker, og en blokk er tett naar mer enn
 * blokk_andel av pikslene i den endret seg. Bladverk i vind gir faa tette
 * blokker; en fugl gir en klynge av dem. Ligger de tette blokkene spredt over
 * mer enn klynge_maks av feltet, er det lys eller vind, ikke én fugl.
 *
 * Nytt her: klyngens omramming kommer med tilbake, som andeler av hele
 * bildet. Det er den utsnittet sentreres paa, og den som avgjoer om
 * telelinsen skal brukes.
 */
fun bevegelseI(forrige: Graa, naa: Graa, k: Konfig, felt: Felt): Maal {
    if (forrige.w != naa.w || forrige.h != naa.h) return Maal(0.0, 0, null)
    val x0 = (felt.x0 * naa.w).toInt().coerceIn(0, naa.w)
    val x1 = (felt.x1 * naa.w).toInt().coerceIn(0, naa.w)
    val y0 = (felt.y0 * naa.h).toInt().coerceIn(0, naa.h)
    val y1 = (felt.y1 * naa.h).toInt().coerceIn(0, naa.h)
    val w = x1 - x0
    val h = y1 - y0
    if (w <= 0 || h <= 0) return Maal(0.0, 0, null)
    val b = max(1, k.blokk)
    val bw = w / b
    val bh = h / b
    val tall = IntArray(max(1, bw * bh))
    var endret = 0
    for (y in y0 until y1) {
        val rad = y * naa.w
        val by = (y - y0) / b
        for (x in x0 until x1) {
            val d = abs((naa.px[rad + x].toInt() and 0xFF) - (forrige.px[rad + x].toInt() and 0xFF))
            if (d > k.diffTerskel) {
                endret++
                val bx = (x - x0) / b
                if (bx < bw && by < bh) tall[by * bw + bx]++
            }
        }
    }
    val andel = endret.toDouble() / (w * h)
    if (bw == 0 || bh == 0) return Maal(andel, 0, null)
    val grense = k.blokkAndel * b * b
    var n = 0
    var bx0 = bw
    var bx1 = -1
    var by0 = bh
    var by1 = -1
    for (by in 0 until bh) for (bx in 0 until bw) {
        if (tall[by * bw + bx] > grense) {
            n++
            bx0 = min(bx0, bx); bx1 = max(bx1, bx)
            by0 = min(by0, by); by1 = max(by1, by)
        }
    }
    if (n == 0) return Maal(andel, 0, null)
    val spredning = (bx1 - bx0 + 1).toDouble() * (by1 - by0 + 1) / (bw * bh)
    if (spredning > k.klyngeMaks) return Maal(andel, 0, null)
    val klynge = Felt(
        (x0 + bx0 * b).toFloat() / naa.w, (y0 + by0 * b).toFloat() / naa.h,
        (x0 + (bx1 + 1) * b).toFloat() / naa.w, (y0 + (by1 + 1) * b).toFloat() / naa.h)
    return Maal(andel, n, klynge)
}
