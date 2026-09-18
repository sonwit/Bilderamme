package no.fugleramme.kamera

import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/**
 * Sender bildene til serveren slik kamera.py gjorde: POST /bilde?stamp=... paa
 * :8091 med JPEG-en i kroppen og metadata i X-Fugl-Meta. Hvert bilde lagres
 * ogsaa i bilder/ paa telefonen (de 200 siste), saa kjor.sh bilder kan hente
 * dem -- ogsaa naar send er av.
 */
class Sender(private val mappe: File) {
    private val traad = Executors.newSingleThreadExecutor()
    private val stampFormat = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.ROOT)
    val sendt = AtomicInteger()
    val lagret = AtomicInteger()
    val feilet = AtomicInteger()

    fun send(jpeg: ByteArray, meta: JSONObject, k: Konfig) {
        val stamp = synchronized(stampFormat) { stampFormat.format(Date()) }
        traad.execute {
            lagre(stamp, jpeg, meta)
            if (!k.send) {
                lagret.incrementAndGet()
                Logg.skriv("lagret kamera_$stamp.jpg paa telefonen (${jpeg.size / 1024} kB); send er av")
                return@execute
            }
            try {
                var url = "${k.server}/bilde?stamp=$stamp"
                if (k.token.isNotEmpty()) url += "&token=" + URLEncoder.encode(k.token, "UTF-8")
                val c = URL(url).openConnection() as HttpURLConnection
                try {
                    c.requestMethod = "POST"
                    c.doOutput = true
                    c.connectTimeout = 10_000
                    c.readTimeout = 30_000
                    c.setRequestProperty("Content-Type", "image/jpeg")
                    // Bare ASCII i metadataene: Android avviser andre tegn i
                    // HTTP-hoder.
                    c.setRequestProperty("X-Fugl-Meta", meta.toString())
                    c.setFixedLengthStreamingMode(jpeg.size)
                    c.outputStream.use { it.write(jpeg) }
                    val kode = c.responseCode
                    val svar = (if (kode < 400) c.inputStream else c.errorStream)
                        ?.bufferedReader()?.use { it.readText() }.orEmpty()
                    val melding = runCatching { JSONObject(svar).optString("message") }.getOrDefault(svar.take(120))
                    if (kode in 200..299) {
                        sendt.incrementAndGet()
                        Logg.skriv("lastet opp kamera_$stamp.jpg (${jpeg.size / 1024} kB) -> $melding")
                    } else {
                        feilet.incrementAndGet()
                        Logg.skriv("opplasting avvist ($kode): $melding")
                    }
                } finally {
                    c.disconnect()
                }
            } catch (e: Exception) {
                feilet.incrementAndGet()
                Logg.skriv("opplasting feilet: ${e.message}")
            }
        }
    }

    private fun lagre(stamp: String, jpeg: ByteArray, meta: JSONObject) {
        try {
            val dir = File(mappe, "bilder").apply { mkdirs() }
            File(dir, "kamera_$stamp.jpg").writeBytes(jpeg)
            File(dir, "kamera_$stamp.json").writeText(meta.toString(2))
            val alle = dir.listFiles()?.sortedBy { it.name } ?: return
            if (alle.size > 400) alle.take(alle.size - 400).forEach { it.delete() }
        } catch (e: Exception) {
            Logg.skriv("kunne ikke lagre bildet paa telefonen: ${e.message}")
        }
    }
}
