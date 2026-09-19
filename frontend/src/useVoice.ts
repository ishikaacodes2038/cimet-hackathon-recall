import { useCallback, useEffect, useRef, useState } from "react";

// Maps our SELECTABLE language codes (matching the backend's
// SUPPORTED_LANGUAGES) to BCP-47 tags for the Web Speech API. "en" and
// "en-AU" are genuinely distinct selections — same script wording, different
// accent — not the same option relabelled. Tagalog uses "tl-PH" rather than
// "fil-PH" for broader real-world browser support.
export const VOICE_LANG_MAP: Record<string, string> = {
  en: "en-US",
  "en-AU": "en-AU",
  hi: "hi-IN",
  fil: "tl-PH",
};

// The agent is one consistent persona — a single voice, for the whole call,
// not whichever voice the browser happens to default to per-utterance. Every
// script (recovery.*.yaml) is written in one consistent grammatical gender
// (feminine, for Hindi) to match. Name substrings are how browsers expose
// gender for built-in voices; this is a best-effort preference list, with a
// deterministic (not random) fallback to the first available voice for the
// language if nothing matches.
const VOICE_NAME_PREFERENCE: Record<string, string[]> = {
  "en-US": ["female", "samantha", "zira", "jenny"],
  "en-AU": ["female", "catherine", "karen", "zira"],
  "hi-IN": ["female", "swara", "heera", "lekha"],
  "tl-PH": ["female", "rosa"],
};

function pickVoice(voices: SpeechSynthesisVoice[], bcp47: string): SpeechSynthesisVoice | null {
  const forLang = voices.filter((v) => v.lang?.toLowerCase() === bcp47.toLowerCase());
  const pool = forLang.length > 0 ? forLang : voices.filter((v) => v.lang?.toLowerCase().startsWith(bcp47.slice(0, 2)));
  if (pool.length === 0) return null;
  const preferences = VOICE_NAME_PREFERENCE[bcp47] ?? ["female"];
  for (const pref of preferences) {
    const match = pool.find((v) => v.name.toLowerCase().includes(pref));
    if (match) return match;
  }
  return pool[0];
}

/**
 * Thin wrapper around the browser's native SpeechRecognition (STT) and
 * SpeechSynthesis (TTS) APIs. Zero vendor account, zero cost, zero backend
 * changes — the recognized text goes through the exact same /voice/message
 * endpoint the typed-text path already uses. This is what actually answers
 * "no real voice input right now": Chrome/Edge only (no standard support in
 * Firefox/Safari), so it degrades to text input automatically when unsupported.
 */
export function useVoice(language: string = "en") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const voiceCacheRef = useRef<Record<string, SpeechSynthesisVoice>>({});
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [supported, setSupported] = useState(true);

  const bcp47 = VOICE_LANG_MAP[language] ?? "en-AU";

  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    const SpeechRecognitionCtor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setSupported(false);
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognitionRef.current = recognition;
  }, []);

  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const cacheVoiceFor = (lang: string) => {
      if (voiceCacheRef.current[lang]) return;
      const voice = pickVoice(window.speechSynthesis.getVoices(), lang);
      if (voice) voiceCacheRef.current[lang] = voice;
    };
    // Voices load asynchronously in most browsers — try immediately, then
    // again once the list is actually populated. Caching means the SAME
    // voice object is reused for every utterance in this language for the
    // rest of the session, rather than being re-resolved (and potentially
    // drifting) on every single speak() call.
    cacheVoiceFor(bcp47);
    window.speechSynthesis.onvoiceschanged = () => cacheVoiceFor(bcp47);
  }, [bcp47]);

  const startListening = useCallback(
    (onFinal: (transcript: string) => void) => {
      const recognition = recognitionRef.current;
      if (!recognition) return;
      // Clicking the mic while the agent is talking is an explicit barge-in —
      // stop the agent immediately rather than talking over the customer.
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      setIsSpeaking(false);
      recognition.lang = bcp47;
      setInterimText("");
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onresult = (event: any) => {
        let interim = "";
        let final = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) final += transcript;
          else interim += transcript;
        }
        setInterimText(interim);
        if (final.trim()) onFinal(final.trim());
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
      setIsListening(true);
      try {
        recognition.start();
      } catch {
        // start() throws if called while already listening — ignore, the
        // existing session continues.
      }
    },
    [bcp47]
  );

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  // "Cut" — stop the agent talking, right now, no matter what it's saying.
  const cutOff = useCallback(() => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string, onDone?: () => void) => {
      if (!("speechSynthesis" in window) || !text) {
        onDone?.();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = bcp47;
      utterance.rate = 1.02;
      const cachedVoice = voiceCacheRef.current[bcp47];
      if (cachedVoice) utterance.voice = cachedVoice;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => {
        setIsSpeaking(false);
        onDone?.();
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
        onDone?.();
      };
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    },
    [bcp47]
  );

  return { supported, isListening, isSpeaking, interimText, startListening, stopListening, speak, cutOff };
}
