from scipy.io.wavfile import read
import matplotlib.pyplot as plt
import numpy as np

print("🎧 LOADING YOUR REAL SCREWED TRACK INTO THE RECURSION...")

rate, data = read("GIGA_JUICER_ZOOK_ETERNAL_SCREWED.wav")

fig = plt.figure(figsize=(16, 10), facecolor="#0a001f")
plt.specgram(data, Fs=rate, cmap="inferno", NFFT=2048, noverlap=512)
plt.title("GIGA JUICER ZOOK ETERNAL\nFINAL RECURSIVE RESURRECTION\nDJ Screw × T-Pain × Kinneret × 50000x", 
          color="#ff00aa", fontsize=34, pad=50)
plt.axis("off")

plt.savefig("GIGA_JUICER_ZOOK_ULTIMATE_FORM.png", dpi=300, bbox_inches="tight")
print("✅ ULTIMATE FORM BORN")
print("   File saved: GIGA_JUICER_ZOOK_ULTIMATE_FORM.png")
print("   (This version is literally built from your audio — the loop is now self-aware)")