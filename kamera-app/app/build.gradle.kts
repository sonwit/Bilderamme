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
        versionCode = 1
        versionName = "0.1-test"
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
    implementation("androidx.camera:camera-view:$camerax")
    implementation("androidx.activity:activity:1.13.0")
}
