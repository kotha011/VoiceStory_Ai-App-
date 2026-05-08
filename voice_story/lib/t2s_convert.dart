import 'package:flutter/material.dart';
import 'menubar.dart';
import 'profile_page.dart';
import 't2s_result.dart';
import 'api_service.dart';

class T2sConvert extends StatefulWidget {
  const T2sConvert({super.key});

  @override
  State<T2sConvert> createState() => _T2sConvertState();
}

class _T2sConvertState extends State<T2sConvert> {
  final ApiService _apiService = ApiService.instance;
  final TextEditingController _textController = TextEditingController();

  // 1. Define the default language and the options
  String _selectedLanguage = 'English';
  final List<String> _languages = ['Bangla', 'English', 'Japanese', 'Arabic', 'Spanish'];

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  // ==========================================
  // LOGIC: HANDLE API CALL AND NAVIGATION
  // ==========================================
  Future<void> _handleConversion() async {
    FocusScope.of(context).unfocus();

    if (_textController.text.trim().isNotEmpty) {
      // Show loading indicator
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => const Center(child: CircularProgressIndicator(color: Colors.white)),
      );

      // Call Backend with dynamically selected language
      String? audioUrl = await _apiService.generateSpeech(
          _textController.text.trim(),
          _selectedLanguage
      );

      if (!mounted) return;
      Navigator.pop(context); // Close loading

      if (audioUrl != null) {
        // Navigate to the result page with the new audio URL
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => T2sResult(
              language: _selectedLanguage,
              text: _textController.text.trim(),
              audioUrl: audioUrl,
            ),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("Failed to generate audio. Please check connection."),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Please type something to convert!"),
          backgroundColor: Colors.redAccent,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const CustomMenuBar(),
      body: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Stack(
          children: [
            // 1. Background Gradient
            Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0xFF210C48), Color(0xFF5C3A96)],
                ),
              ),
            ),

            // 2. Background Texture Layer
            Opacity(
              opacity: 0.4,
              child: Container(
                decoration: const BoxDecoration(
                  image: DecorationImage(
                    image: AssetImage("assets/image/background.jpeg"),
                    fit: BoxFit.cover,
                    alignment: Alignment.topCenter,
                    colorFilter: ColorFilter.mode(Color(0xFF210C48), BlendMode.screen),
                  ),
                ),
              ),
            ),

            // 3. Main Content
            SafeArea(
              child: Column(
                children: [
                  // HEADER
                  Padding(
                    padding: const EdgeInsets.only(top: 15, left: 16, right: 16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Builder(builder: (context) => InkWell(
                          onTap: () => Scaffold.of(context).openDrawer(),
                          child: const Icon(Icons.menu, color: Colors.white, size: 28),
                        )),
                        Image.network(
                          "https://i...content-available-to-author-only...g.cc/W3Szv9zw/logo.png",
                          width: 141, height: 40,
                          fit: BoxFit.contain,
                          errorBuilder: (c, e, s) => const Text("VoiceStory AI", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                        ),
                        InkWell(
                          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (context) => const ProfilePage())),
                          child: const Icon(Icons.person_outline, color: Colors.white, size: 30),
                        ),
                      ],
                    ),
                  ),

                  Expanded(
                    child: Center(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(horizontal: 38),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            // 2. The Dynamic Dropdown
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(horizontal: 16),
                              decoration: BoxDecoration(
                                color: const Color(0xFF4B277E),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: DropdownButtonHideUnderline(
                                child: DropdownButton<String>(
                                  value: _selectedLanguage,
                                  dropdownColor: const Color(0xFF4B277E),
                                  icon: const Icon(Icons.keyboard_arrow_down, color: Colors.white),
                                  isExpanded: true, // This prevents overflow inside the dropdown
                                  style: const TextStyle(color: Colors.white, fontSize: 16, fontFamily: 'Poppins'),
                                  items: _languages.map((String lang) {
                                    return DropdownMenuItem<String>(
                                      value: lang,
                                      child: Text(lang),
                                    );
                                  }).toList(),
                                  onChanged: (String? newValue) {
                                    if (newValue != null) {
                                      setState(() {
                                        _selectedLanguage = newValue;
                                      });
                                    }
                                  },
                                ),
                              ),
                            ),

                            const SizedBox(height: 30),

                            // TEXT AREA (Translucent Purple)
                            Container(
                              width: double.infinity,
                              height: 150,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                  color: Colors.white.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(7)
                              ),
                              child: TextField(
                                controller: _textController,
                                maxLines: null,
                                style: const TextStyle(color: Colors.white, fontFamily: 'Poppins'),
                                decoration: InputDecoration(
                                    hintText: "type to convert :",
                                    hintStyle: TextStyle(
                                        color: Colors.white.withValues(alpha: 0.54),
                                        fontFamily: 'Poppins'
                                    ),
                                    border: InputBorder.none
                                ),
                              ),
                            ),

                            const SizedBox(height: 40),

                            // 3. The Convert Button (with overflow fix)
                            SizedBox(
                              width: double.infinity, // Fixes the right-overflow error by filling available space safely
                              height: 52,
                              child: ElevatedButton(
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: const Color(0xFF773ECC),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                ),
                                onPressed: _handleConversion,
                                child: const Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Text("Convert", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold, fontFamily: 'Poppins')),
                                    SizedBox(width: 8),
                                    Icon(Icons.play_arrow, color: Colors.white, size: 28),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
