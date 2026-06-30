import 'package:geocoding/geocoding.dart';
import 'package:geolocator/geolocator.dart';

/// Resolves device location to a human-readable city + country code.
class DeviceLocation {
  static Future<({String city, String countryCode})?> getCityAndCountry() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return null;

      LocationPermission perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
        if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
          return null;
        }
      }
      if (perm == LocationPermission.deniedForever) return null;

      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.low),
      );

      final placemarks = await placemarkFromCoordinates(pos.latitude, pos.longitude);
      if (placemarks.isEmpty) return null;

      final pm = placemarks.first;
      final city = pm.locality ?? pm.administrativeArea ?? pm.subAdministrativeArea ?? '';
      final country = pm.isoCountryCode ?? '';
      if (city.isEmpty || country.isEmpty) return null;
      return (city: city, countryCode: country);
    } catch (_) {
      return null;
    }
  }
}
