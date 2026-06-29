import 'dart:convert';

import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import '../config.dart';

class SocialAuthService {
  static final _google = GoogleSignIn(scopes: ['email']);

  static Future<Map<String, dynamic>?> signInWithGoogle(String? serverToken) async {
    final account = await _google.signIn();
    if (account == null) return null;
    final auth = await account.authentication;
    final idToken = auth.idToken;
    if (idToken == null) throw Exception('No ID token from Google');
    final headers = <String, String>{
      'Content-Type': 'application/json',
      if (serverToken != null) 'Authorization': 'Bearer $serverToken',
    };
    final r = await http
        .post(
          Uri.parse('${AppConfig.apiBase}/auth/google'),
          headers: headers,
          body: jsonEncode({'id_token': idToken}),
        )
        .timeout(const Duration(seconds: 12));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>?> signInWithApple(String? serverToken) async {
    final credential = await SignInWithApple.getAppleIDCredential(
      scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
    );
    final headers = <String, String>{
      'Content-Type': 'application/json',
      if (serverToken != null) 'Authorization': 'Bearer $serverToken',
    };
    final r = await http
        .post(
          Uri.parse('${AppConfig.apiBase}/auth/apple'),
          headers: headers,
          body: jsonEncode({
            'identity_token': credential.identityToken,
            'email': credential.email,
          }),
        )
        .timeout(const Duration(seconds: 12));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }
}
