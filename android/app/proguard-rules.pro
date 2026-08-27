# Keep Hilt/Room/Retrofit
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }
-keep class * extends dagger.hilt.android.HiltAndroidApp
-keepclasseswithmembers class * { @dagger.hilt.android.AndroidEntryPoint <methods>; }
-keep class androidx.room.** { *; }
-dontwarn org.codehaus.mojo.animal_sniffer.IgnoreJRERequirement
