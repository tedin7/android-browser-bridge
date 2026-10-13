plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "net.arvos.browserbridge.companion"
    compileSdk = 35
    defaultConfig {
        applicationId = "net.arvos.browserbridge.companion"
        minSdk = 26
        targetSdk = 35
        versionCode = 10
        versionName = "0.2.3-experimental"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildTypes { release { isMinifyEnabled = false } }
}
dependencies { testImplementation("junit:junit:4.13.2") }
