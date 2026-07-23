import 'package:flutter/material.dart';

/// LaundryConnect brand theme: professional minimalist, navy and teal,
/// strong readability, practical industrial feel. No decorative clutter.
abstract final class AppColors {
  static const navy = Color(0xFF122B47);
  static const navyDark = Color(0xFF0B1C30);
  static const teal = Color(0xFF00897B);
  static const tealLight = Color(0xFF4DB6AC);
  static const surface = Color(0xFFF6F8FA);
  static const warning = Color(0xFFB26A00);
  static const danger = Color(0xFFB3261E);
}

ThemeData buildAppTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: AppColors.navy,
    primary: AppColors.navy,
    secondary: AppColors.teal,
    surface: AppColors.surface,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: AppColors.surface,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.navy,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    cardTheme: CardThemeData(
      elevation: 1,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.teal,
        foregroundColor: Colors.white,
      ),
    ),
  );
}
