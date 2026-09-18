package no.fugleramme.kamera

import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Loggen: logcat, logg.txt i appens mappe (kjor.sh logg) og de siste linjene til skjermen. */
object Logg {
    private var fil: File? = null
    private val siste = ArrayDeque<String>()
    private val tid = SimpleDateFormat("MM-dd HH:mm:ss", Locale.ROOT)

    fun init(mappe: File) {
        fil = File(mappe, "logg.txt")
    }

    @Synchronized
    fun skriv(s: String) {
        Log.i("Fuglekamera", s)
        val linje = "${tid.format(Date())} $s"
        siste.addLast(linje)
        while (siste.size > 8) siste.removeFirst()
        val f = fil ?: return
        try {
            if (f.length() > 2_000_000) f.writeText(f.readText().takeLast(1_000_000))
            f.appendText(linje + "\n")
        } catch (e: Exception) {
            Log.w("Fuglekamera", "kunne ikke skrive logg.txt: ${e.message}")
        }
    }

    @Synchronized
    fun sisteLinjer(): List<String> = siste.toList()
}
