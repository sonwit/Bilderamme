plugins {
    id("com.android.application")
}

android {
    namespace = "no.fugleramme.kamera"
    compileSdk = 37

    defaultConfig {
        applicationId = "no.fugleramme.kamera"
        // Pixel 9 Pro kom med Android 14.
        minSdk = 34
        targetSdk = 37
        versionCode = 2
        versionName = "0.2"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    val camerax = "1.6.2"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.activity:activity:1.13.0")
}
