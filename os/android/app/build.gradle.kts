// LibertyRecomp Android — :app module.
//
// Gradle never runs CMake. The native side (libmain.so, librexruntime.so,
// the GPU plugins, libSDL3.so, libc++_shared.so) is millions of lines of
// recompiled PowerPC and is built by os/android/scripts/build_native.sh,
// which stages the libraries into src/main/jniLibs and the title resources
// into src/main/assets/Resources. This module only packages them.
//
// The SDL Java classes come from the same SDL3 tree the native library is
// built from: SDLActivity refuses to start when the versions differ.

plugins {
    id("com.android.application")
}

val sdlJavaDir = rootProject.file(
    "../../glue/rexglue-sdk-main/thirdparty/sdl3/android-project/app/src/main/java")
val eflcStartTest = providers.gradleProperty("eflcStartTest").orNull == "true"

android {
    namespace   = "com.libertyrecomp"
    compileSdk  = 35
    ndkVersion  = "29.0.14206865"

    defaultConfig {
        // Side-by-side test install: never replace the original application's saves.
        applicationId = if (eflcStartTest) "com.libertyrecomp.eflctest" else "com.libertyrecomp.thor"
        // 28: ASharedMemory (26) for guest memory and AAudio (27) for audio.
        minSdk        = 29
        targetSdk     = 35
        versionCode   = if (eflcStartTest) 20004 else 10001
        versionName   = if (eflcStartTest) "0.5.9-eflc-start-test.4" else "0.5.9-thor-test.1"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    sourceSets["main"].java.srcDirs("src/main/java", sdlJavaDir)
    if (eflcStartTest) {
        sourceSets["main"].java.srcDir("src/eflc/java")
        sourceSets["main"].manifest.srcFile("src/eflc/AndroidManifest.xml")
    }

    buildTypes {
        debug {
            isDebuggable    = true
            isJniDebuggable = true
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
            signingConfig   = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        jniLibs {
            // Unpack the libraries into nativeLibraryDir: the runtime finds its
            // GPU plugins by real path next to itself, and a Turnip driver
            // loaded through libadrenotools needs real files as well.
            useLegacyPackaging = true
            // build_native.sh decides what is stripped.
            keepDebugSymbols += "**/*.so"
        }
    }

    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
}
