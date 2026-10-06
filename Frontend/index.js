// --- Constants ---
const VOICES = {
  English: { Male: "Matthew", Female: "Alicia" },
  Hindi: { Male: "Aman", Female: "Namrita" },
  Tamil: { Male: "Murali", Female: "Iniya" },
  Telugu: { Male: "Zion", Female: "Josie" }
};

const LOCALES = {
  English: "en-US",
  Hindi: "hi-IN",
  Tamil: "ta-IN",
  Telugu: "te-IN"
};

// --- State ---
const state = {
  place: '',
  image: '',
  length: 'Summary',
  voice: 'Male',
  isSpeakingFallback: false
};

// --- DOM Elements ---
const cardsContainer = document.querySelector('.cards');
const experiencePanel = document.getElementById('experience');
const previewTitle = document.getElementById('previewTitle');
const audioSection = document.getElementById('audioSection');
const audioPlayer = document.getElementById('audioPlayer');
const transcriptText = document.getElementById('scriptText');
const generateButton = document.getElementById('generateBtn');
const languageSelect = document.getElementById('selectLanguage');
const closeButton = document.getElementById('closeExperience');
const searchPreviewCard = document.getElementById('searchPreviewCard');
const searchPreviewImage = document.getElementById('searchPreviewImage');
const searchPreviewTitle = document.getElementById('searchPreviewTitle');
const transcriptToggle = document.getElementById('transcriptToggle');
const transcriptContent = document.getElementById('transcriptContent');
const transcriptArrow = document.getElementById('transcriptArrow');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');

// --- Functions ---

function selectDestination(place, image, clickedCard = null) {
  state.place = place;
  state.image = image;

  // Stop any active speech synthesis
  stopBrowserSpeech();

  // Update UI content
  previewTitle.textContent = place;
  cardsContainer.classList.add('faded');

  // Reset previous states
  document.querySelectorAll('.place-card').forEach(card => card.classList.remove('active'));
  searchPreviewCard.classList.add('hidden');

  // Handle Card Visibility
  if (clickedCard) {
    clickedCard.classList.add('active');
  } else {
    // If it's a search result, show the preview card
    searchPreviewImage.src = image || 'https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=800&q=80';
    searchPreviewTitle.textContent = place;
    searchPreviewCard.classList.remove('hidden');
    searchPreviewCard.classList.add('active');
  }

  // Reset Audio Panel
  audioSection.classList.add('hidden');
  audioPlayer.src = '';
  transcriptText.textContent = '';
  const oldNotice = document.getElementById('audioNoticeBanner');
  if (oldNotice) oldNotice.remove();
  const oldFallbackBtn = document.getElementById('browserSpeechBtn');
  if (oldFallbackBtn) oldFallbackBtn.remove();
  generateButton.textContent = 'Generate Audio Guide';
  generateButton.disabled = false;

  // Show Panel with animation
  experiencePanel.classList.remove('hidden');
  setTimeout(() => {
    experiencePanel.classList.add('visible');
    experiencePanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 10);
}

function deselectDestination() {
  stopBrowserSpeech();
  experiencePanel.classList.remove('visible');

  // Wait for animation to finish before hiding
  setTimeout(() => {
    experiencePanel.classList.add('hidden');
    cardsContainer.classList.remove('faded');
    searchPreviewCard.classList.add('hidden');
    document.querySelectorAll('.place-card').forEach(card => card.classList.remove('active'));
  }, 300);
}

function stopBrowserSpeech() {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  state.isSpeakingFallback = false;
}

function playBrowserSpeech(text, lang) {
  if (!('speechSynthesis' in window)) return;
  stopBrowserSpeech();

  const utterance = new SpeechSynthesisUtterance(text);
  const localeMap = {
    English: 'en-US',
    Hindi: 'hi-IN',
    Tamil: 'ta-IN',
    Telugu: 'te-IN'
  };
  utterance.lang = localeMap[lang] || 'en-US';
  utterance.rate = 0.95;

  utterance.onend = () => {
    state.isSpeakingFallback = false;
    updateListenButton(false);
  };
  utterance.onerror = () => {
    state.isSpeakingFallback = false;
    updateListenButton(false);
  };

  state.isSpeakingFallback = true;
  updateListenButton(true);
  window.speechSynthesis.speak(utterance);
}

function updateListenButton(isSpeaking) {
  const fallbackBtn = document.getElementById('browserSpeechBtn');
  if (fallbackBtn) {
    fallbackBtn.innerHTML = isSpeaking ? '⏹ Stop Voice' : '🔊 Listen with Browser Voice';
  }
}

// Search functionality
function handleSearch() {
  if (!searchInput) return;
  const query = searchInput.value.trim();
  if (!query) return;

  const placeCards = Array.from(document.querySelectorAll('.place-card:not(.search-preview-card)'));
  const foundCard = placeCards.find(card =>
    card.dataset.place.toLowerCase().includes(query.toLowerCase())
  );

  if (foundCard) {
    selectDestination(foundCard.dataset.place, foundCard.dataset.image, foundCard);
  } else {
    // Custom destination search
    const customImage = 'https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=800&q=80';
    selectDestination(query, customImage, null);
  }
}

// --- Event Listeners ---

// Close Button
if (closeButton) {
  closeButton.addEventListener('click', deselectDestination);
}

// Search Inputs & Buttons
if (searchBtn) {
  searchBtn.addEventListener('click', handleSearch);
}
if (searchInput) {
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSearch();
    }
  });
}

// Card Clicks
document.querySelectorAll('.place-card:not(.search-preview-card)').forEach(card => {
  card.addEventListener('click', () => {
    selectDestination(card.dataset.place, card.dataset.image, card);
  });
});

// Option Toggles (History Type)
const lengthButtons = document.querySelectorAll('[data-group="length"] button');
lengthButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    lengthButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.length = btn.dataset.value;
  });
});

// Option Toggles (Voice Gender)
const voiceButtons = document.querySelectorAll('[data-group="voice"] button');
voiceButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    voiceButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.voice = btn.dataset.value;
  });
});

// Backend connection configuration
const LOCAL_BACKEND_URL = "http://127.0.0.1:5000";
const RENDER_BACKEND_URL = "https://travel-guide-cijv.onrender.com";

const backendUrl =
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1"
    ? LOCAL_BACKEND_URL
    : RENDER_BACKEND_URL;

generateButton.addEventListener('click', async () => {
  if (!state.place) {
    alert('Please select or search for a destination first.');
    return;
  }

  generateButton.disabled = true;
  generateButton.textContent = '⏳ Generating Guide...';

  try {
    const selectedLanguage = languageSelect.value;
    const selectedVoice = state.voice;

    const response = await fetch(`${backendUrl}/generate-audio-guide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        place: state.place,
        answerType: state.length,
        language: selectedLanguage,
        voiceId: VOICES[selectedLanguage]?.[selectedVoice] || 'Matthew',
        locale: LOCALES[selectedLanguage] || 'en-US'
      })
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.error || `Server responded with status ${response.status}`);
    }

    const data = await response.json();

    // 1. Display Gemini-generated description
    transcriptText.textContent = data.description || '';
    audioSection.classList.remove('hidden');

    // Automatically expand transcript
    transcriptContent.classList.remove('hidden');
    transcriptArrow.classList.add('rotate-180');

    // 2. Display backend audio notice if present
    let noticeEl = document.getElementById('audioNoticeBanner');
    if (data.audioNotice) {
      if (!noticeEl) {
        noticeEl = document.createElement('div');
        noticeEl.id = 'audioNoticeBanner';
        audioSection.insertBefore(noticeEl, audioSection.firstChild);
      }
      noticeEl.className = 'mb-4 p-3.5 text-xs rounded-xl bg-amber-50 border border-amber-200 text-amber-800 flex items-start gap-2 leading-relaxed';
      noticeEl.innerHTML = `<span class="text-sm">ℹ️</span> <div><strong class="font-semibold block">Notice:</strong>${data.audioNotice}</div>`;
      noticeEl.classList.remove('hidden');
    } else if (noticeEl) {
      noticeEl.remove();
    }

    // Remove any previous browser fallback button
    const oldFallbackBtn = document.getElementById('browserSpeechBtn');
    if (oldFallbackBtn) oldFallbackBtn.remove();

    // 3. Display Murf Audio and Audio player
    if (data.audioBase64) {
      audioPlayer.src = `data:audio/mp3;base64,${data.audioBase64}`;
      audioPlayer.load();
      audioPlayer.classList.remove('hidden');
      generateButton.textContent = 'Audio Guide Ready!';
      setTimeout(() => {
        generateButton.textContent = 'Generate Audio Guide';
        generateButton.disabled = false;
      }, 2000);
    } else {
      // Murf audio not available (e.g. key missing/masked or notice returned)
      audioPlayer.classList.add('hidden');
      generateButton.textContent = 'Audio Guide Ready';
      generateButton.disabled = false;

      // Provide browser voice playback button
      const browserSpeechBtn = document.createElement('button');
      browserSpeechBtn.id = 'browserSpeechBtn';
      browserSpeechBtn.className = 'w-full mt-3 py-3 px-4 rounded-xl border border-orange-200 bg-orange-50 text-[#ff8a1f] font-semibold text-xs hover:bg-orange-100 transition-all flex items-center justify-center gap-2 shadow-sm';
      browserSpeechBtn.innerHTML = '🔊 Listen with Browser Voice';
      browserSpeechBtn.addEventListener('click', () => {
        if (state.isSpeakingFallback) {
          stopBrowserSpeech();
          updateListenButton(false);
        } else {
          playBrowserSpeech(data.description, selectedLanguage);
        }
      });
      audioSection.appendChild(browserSpeechBtn);
    }

  } catch (err) {
    console.error('Error generating guide:', err);
    alert(`Generation failed: ${err.message || 'Please check that the Backend server is running.'}`);
    generateButton.textContent = 'Generate Audio Guide';
    generateButton.disabled = false;
  }
});

// Transcript Toggle
if (transcriptToggle) {
  transcriptToggle.addEventListener('click', () => {
    transcriptContent.classList.toggle('hidden');
    transcriptArrow.classList.toggle('rotate-180');
  });
}
