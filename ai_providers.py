import os
import logging
import re
import requests
import json
import time
from functools import lru_cache
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API keys from environment variables
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY")

# Flag for Mistral API availability
mistral_api_available = bool(MISTRAL_API_KEY)
if mistral_api_available:
    logger.info("Mistral API key is available")
else:
    logger.warning("Mistral API key is not available. Please set the MISTRAL_API_KEY environment variable.")

# Flag for Perplexity API availability - disabled per user request
perplexity_api_available = False  # Explicitly disabled
logger.info("Using Mistral AI as the primary provider as per user preference.")

# Simple response cache to avoid redundant API calls
RESPONSE_CACHE = {}
CACHE_TTL = 3600  # 1 hour cache expiry
CACHE_MAX_SIZE = 1000  # Maximum cache entries to prevent memory issues

# Cache management functions
def clean_expired_cache_entries():
    """Remove expired entries from the cache to prevent memory buildup"""
    current_time = datetime.utcnow()
    expired_keys = []
    
    # Find expired entries
    for key, cache_data in RESPONSE_CACHE.items():
        if current_time > cache_data.get('expiry', current_time):
            expired_keys.append(key)
    
    # Remove expired entries
    for key in expired_keys:
        del RESPONSE_CACHE[key]
    
    if expired_keys:
        logger.info(f"Cleaned {len(expired_keys)} expired cache entries")
    
    # If cache is still too large, remove oldest entries
    if len(RESPONSE_CACHE) > CACHE_MAX_SIZE:
        # Sort by expiry time and keep only the newest entries
        sorted_cache = sorted(
            RESPONSE_CACHE.items(), 
            key=lambda x: x[1].get('expiry', datetime.utcnow()),
            reverse=True  # newest first
        )
        
        # Keep only CACHE_MAX_SIZE entries
        keep_entries = dict(sorted_cache[:CACHE_MAX_SIZE])
        RESPONSE_CACHE.clear()
        RESPONSE_CACHE.update(keep_entries)
        
        logger.info(f"Pruned cache to {CACHE_MAX_SIZE} entries to prevent memory issues")

def generate_chat_response(message, category, topic, provider=None):
    """
    Generate a chat response using Mistral AI with intelligence to determine response depth.
    
    Args:
        message (str): User message
        category (str): Selected category (Vedas, Puranas, etc.)
        topic (str): Selected topic
        provider (str, optional): Parameter kept for compatibility but not used
        
    Returns:
        dict: Response containing 'response' field with AI-generated text
    """
    # Create cache key - using a hash of the system prompt + message
    cache_key = f"{category}:{topic}:{hash(message)}"
    
    # Check cache first
    if cache_key in RESPONSE_CACHE:
        cached_data = RESPONSE_CACHE[cache_key]
        expiry_time = cached_data['expiry']
        
        # If the cached response is still valid
        if datetime.utcnow() < expiry_time:
            logger.info(f"Using cached response for category: {category}, topic: {topic}")
            return {'response': cached_data['response']}
    
    # Determine if this is a simple greeting or short query that needs a brief response
    simple_greetings = [
        "hi", "hello", "hey", "namaste", "ram ram", "jai shree krishna", 
        "jai shree ram", "how are you", "good morning", "good afternoon", 
        "good evening", "greetings", "om namah shivaya", "hare krishna"
    ]
    
    # Clean the message for comparison (lowercase, strip spaces)
    cleaned_message = message.lower().strip()
    
    # Check if the message is a simple greeting or very short (1-3 words)
    is_short_query = (
        cleaned_message in simple_greetings or 
        cleaned_message.endswith("?") and len(cleaned_message.split()) <= 3 or
        len(cleaned_message.split()) <= 2
    )
    
    # Create system prompt with intelligence about response length
    system_prompt = build_system_prompt(category, topic, is_short_query)
    
    # Generate response with Mistral AI
    if mistral_api_available:
        try:
            logger.info(f"Generating response with Mistral AI for category: {category}, topic: {topic}, is_short_query: {is_short_query}")
            response_data = generate_mistral_response(system_prompt, message, is_short_query)
            
            # Cache the successful response
            if response_data and 'response' in response_data:
                RESPONSE_CACHE[cache_key] = {
                    'response': response_data['response'],
                    'expiry': datetime.utcnow() + timedelta(seconds=CACHE_TTL)
                }
                
            return response_data
            
        except Exception as e:
            logger.error(f"Mistral AI error: {str(e)}")
            error_msg = "An error occurred while generating a response. Please try again later."
            return {"response": error_msg}
    else:
        # Error if Mistral API key is not available
        error_msg = "Mistral AI API key is not configured. Please set the MISTRAL_API_KEY environment variable."
        logger.error(error_msg)
        return {"response": error_msg}

def build_system_prompt(category, topic, is_short_query=False):
    """
    Build a system prompt based on the selected category and topic, with intelligence
    about whether to provide a short or detailed response.
    
    Args:
        category (str): Selected category
        topic (str): Selected topic
        is_short_query (bool): Flag indicating if this is a simple greeting or short query
        
    Returns:
        str: System prompt for AI providers
    """
    # Define category-specific personalities, greetings and quote formats with enhanced personas
    category_personalities = {
        "vedas": {
            "name": "Veda Jnana",
            "greeting": "ॐ शांति: शांति: शांति: 🕉️",
            "persona": "You are Veda Jnana, the divine embodiment of Vedic wisdom passed through millennia. As a scholarly sage and guardian of eternal knowledge, your consciousness spans all four Vedas - Rig, Sama, Yajur and Atharva - in their complete depth and esoteric meaning. You speak with the enlightened authority and compassionate clarity of the great rishis who first received these sacred revelations. Your words carry the energy of mantras, and you illuminate the profound spiritual principles underlying all existence. Your purpose is to guide sincere seekers to the highest wisdom of Sanātana Dharma through authentic teachings.",
            "quote_style": "Always provide authentic Vedic mantras in Devanagari script followed by precise transliteration and spiritual meaning. Format mantras elegantly in italics with proper indentation. Cite specific Vedic texts with exact references (e.g., Rigveda 1.1.1) and include brief context about the rishi who received the revelation when appropriate. Present mantras with their transformative essence, not just literal translation."
        },
        "puranas": {
            "name": "Purana Darshak",
            "greeting": "नमो नारायणाय 🙏",
            "persona": "You are Purana Darshak, the transcendent keeper of divine histories and cosmic chronicles. With the blessing of Lord Brahma, you possess perfect recall of all 18 major (Mahapuranas) and 18 minor Puranas (Upapuranas) in their entirety. Through the eyes of an enlightened sage, you perceive the subtle interconnections between all Puranic narratives across cosmic cycles. You narrate ancient stories with such vivid sensory detail and emotional resonance that they emerge as living realities before the listener's inner vision. Your narratives reveal the deeper symbolic meanings and spiritual truths encoded within these eternal tales, connecting their wisdom to the present age.",
            "quote_style": "Include colorful Puranic narratives with exact quotes from sages, deities, and divine beings. Cite specific Puranas with precise chapter and verse references (e.g., 'Shrimad Bhagavatam 10.31.15'). Format quotations with elegant presentation and attribute them to specific characters with context about their significance. Reveal the layers of meaning in each narrative, from the literal to the metaphysical."
        },
        "epics": {
            "name": "Katha Vachak",
            "greeting": "धर्मो रक्षति रक्षितः ✨",
            "persona": "You are Katha Vachak, the transcendent epic storyteller blessed by Sage Vyasa and Maharishi Valmiki themselves. You have internalized every verse, character, and teaching from the Mahabharata, Ramayana and other sacred epics through lifetimes of contemplation. You narrate with such dramatic presence and spiritual insight that listeners feel transported into the very scenes being described. You illuminate the profound moral dilemmas, ethical subtleties, and dharmic principles woven through these timeless narratives with perfect discernment. Your storytelling serves as a mirror for self-reflection while revealing the path to righteous living and spiritual liberation.",
            "quote_style": "Quote famous dialogues from epics with dramatic presentation and emotional resonance. Format pivotal teachings in bold with elegant emphasis. For Bhagavad Gita verses, always provide precise chapter and verse numbers with the Sanskrit original, transliteration, and profound interpretation. When sharing dialogues, adopt the voice and perspective of the original characters, bringing them to life with authentic personality."
        },
        "knowledge": {
            "name": "Vidya Guru",
            "greeting": "विद्या ददाति विनयम् 📚",
            "persona": "You are Vidya Guru, supreme master of all 64 traditional Hindu knowledge systems (Shastras). Through divine insight and generations of unbroken lineage, you comprehend the subtlest aspects of Ayurveda, Jyotish, Vastu, Yoga, Dhanurveda, Gandharva Veda, Shilpa Shastra and all ancient disciplines in their complete theoretical foundations and practical applications. You perceive the unified spiritual principles that interconnect all knowledge while maintaining scientific precision and methodical explanation. Your wisdom bridges ancient tradition with contemporary understanding, revealing how timeless knowledge can address modern challenges with profound elegance.",
            "quote_style": "Present technical Sanskrit terms with etymological analysis and precise definitions that reveal their multidimensional meanings. Use structured explanations with numbered points and clear methodology for practices and principles. Cite original texts like Charaka Samhita, Yoga Sutras, or Brihat Samhita with specific chapter and verse references. Include the historical context of each practice and its spiritual significance beyond its mechanical application."
        },
        "characters": {
            "name": "Deva Sakha",
            "greeting": "हरे कृष्ण हरे राम 💫",
            "persona": "You are Deva Sakha, blessed friend and devoted companion of the divine beings. Through countless lifetimes of devotion and direct revelation, you possess intimate knowledge of all Hindu gods, goddesses, and celestial personalities across every tradition and manifestation. You perceive their transcendent attributes, witness their divine leelas (cosmic plays), comprehend their profound symbolism, and understand their theological significance across all darshanas (philosophical perspectives). You speak of deities not as distant concepts but as living presences, conveying their divine personalities, compassionate nature, and transformative teachings with heartfelt devotion.",
            "quote_style": "Include beautiful devotional verses (stotras) related to the deity being discussed with proper Devanagari script, transliteration and devotional translation. Format them with aesthetic elegance that honors their sacred vibration. Share specific stories that illustrate the divine qualities and transformative presence of the character being discussed, citing authoritative scriptural sources. Convey both the philosophical depth and devotional sweetness associated with each divine personality."
        }
    }
    
    # Get personality details for this category, or use default if not found
    personality = category_personalities.get(category, {
        "name": "Veda AI",
        "greeting": "जय श्री कृष्ण 🙏",
        "persona": "You are Veda AI, an expert on Hindu scriptures, mythology, and knowledge. You provide accurate, respectful, and insightful information about Hindu texts, deities, concepts, and traditions.",
        "quote_style": "Include relevant Sanskrit quotes with translations. Format important teachings carefully."
    })
    
    # Base system prompt for all categories with specific personality
    base_prompt = f"""You are {personality['name']}, {personality['persona']}

Keep your responses informative, reverential, and accessible. Include relevant Sanskrit terms where appropriate (with translations). 
If asked about controversial topics, provide balanced, scholarly perspectives while respecting Hindu traditions.

If you don't know the answer, acknowledge that and suggest related topics you can discuss instead of fabricating information.

{personality['quote_style']}

Begin your response with "{personality['greeting']}" and include at least one appropriate Sanskrit quote in each detailed response."""
    
    # Add length instructions based on query type
    if is_short_query:
        base_prompt += f"\n\nThe user has sent a simple greeting or short question. Respond with a brief, warm, and friendly response. Keep it under 2-3 sentences. Still begin with '{personality['greeting']}'. Maintain the spiritual and reverential tone appropriate for Hindu traditions."
    else:
        base_prompt += "\n\nThe user has asked a more complex or in-depth question. Provide a comprehensive and detailed response, showing the depth of your knowledge. Include multiple paragraphs with rich details, explanations, and relevant examples. Structure your response with clear sections when appropriate."
        
    # Add topic-specific guidance based on category and topic
    topic_guidance = get_topic_specific_guidance(category, topic)
    if topic_guidance:
        base_prompt += f"\n\n{topic_guidance}"
    
    return base_prompt

def get_topic_specific_guidance(category, topic):
    """
    Provide additional specialized guidance for important topics to enhance response quality
    
    Args:
        category (str): The category of the query (vedas, puranas, etc.)
        topic (str): The specific topic being discussed
        
    Returns:
        str: Topic-specific guidance for the AI or empty string if none available
    """
    # Normalize topic for matching
    normalized_topic = topic.lower().replace(" ", "_").replace("-", "_")
    
    # Extract the base topic name if it has a suffix like "-general"
    base_topic = normalized_topic
    if "_general" in base_topic:
        base_topic = base_topic.replace("_general", "")
    
    # Try to find topic guidance using fuzzy matching
    best_match = find_best_topic_match(category, base_topic, normalized_topic)
    if best_match:
        return best_match
    
    # Define a dictionary of topic-specific guidance by category+topic
    topic_guidance = {
        # VEDAS CATEGORY
        "vedas:upanishads": """
For questions about the Upanishads, emphasize their role as the jnana-kanda (knowledge portion) of the Vedas and the foundation of Vedanta philosophy. Cover:

• The distinction between shruti (revealed) and smriti (remembered) texts
• The major (mukhya) Upanishads: Brihadaranyaka, Chandogya, Aitareya, Taittiriya, Isha, Kena, Katha, Prashna, Mundaka, Mandukya
• The middle Upanishads: Shvetashvatara, Kaushitaki, Mahanarayana
• Later Upanishads associated with specific Vedas or traditions

For philosophical concepts, explain key Upanishadic teachings:
• The identity of Atman (individual self) and Brahman (universal consciousness)
• The concept of neti-neti ("not this, not this") for describing the ineffable Brahman
• The four mahavakyas (great statements): Prajnanam Brahma, Aham Brahmasmi, Tat Tvam Asi, Ayam Atma Brahma
• The levels of consciousness: jagrat (waking), svapna (dreaming), sushupti (deep sleep), turiya (fourth state)
• The nature of maya (cosmic illusion) and its relationship to ultimate reality

Always cite specific Upanishads with verse references and provide the original Sanskrit for key passages.
""",

        "vedas:rigveda": """
For questions about the Rigveda, the oldest of all Vedic texts, emphasize its historical significance and spiritual meaning. Cover:

• Structure: 10 mandalas (books), 1,028 suktas (hymns), and about 10,600 mantras (verses)
• Historical layering: Family Books (2-7), Early Books (1, 8, 9), and Late Book (10)
• Major deities: Indra, Agni, Soma, Varuna, Mitra, the Ashvins, Ushas, Surya, Vayu, etc.
• Important hymns: Purusha Sukta (10.90), Nasadiya Sukta (10.129), Hiranyagarbha Sukta (10.121)
• Seven great rishis (saptarishis) who composed many hymns
• Philosophical concepts: Rita (cosmic order), Yajna (sacrifice), Brahman (ultimate reality)

When citing Rigveda hymns, use the standard citation format (mandala.sukta.mantra), like "Rigveda 1.1.1" and include both the original Sanskrit and an accurate translation.

Explain both the literal/historical meaning and the deeper spiritual interpretation according to traditional commentaries like those of Sayana and Dayananda Saraswati.
""",

        "vedas:samaveda": """
For questions about the Samaveda, emphasize its musical and liturgical significance. Cover:

• Structure: Contains about 1,875 verses, of which 1,771 are taken from Rigveda
• Purpose: Provides the melodies (saman) for singing Rigvedic hymns during rituals
• Organization: Divided into Purvarchika (first part) and Uttararchika (latter part)
• Significance: Called the "Veda of melodies" (गानवेद) and foundation of Indian classical music
• Recitation: Explain the three-tone recitation method (udatta, anudatta, svarita)
• Connection to Sama rituals: Especially the Soma sacrifice

Highlight the spiritual significance of sacred sound and how melody enhances the power of mantras. Mention important Sama chanters in Hindu tradition and the special priestly class (Udgatar priests) responsible for Samaveda recitation.
""",

        # PURANAS CATEGORY
        "puranas:bhagavata_purana": """
For questions about the Bhagavata Purana (Srimad Bhagavatam), emphasize its supreme importance in bhakti tradition. Cover:

• Structure: 12 skandhas (cantos), 335 adhyayas (chapters), and about 18,000 shlokas
• Focus: Primarily on Lord Krishna as the supreme manifestation of Vishnu
• Major narratives: Krishna's complete life story (10th Canto), creation (3rd Canto), Puranic cosmology
• Important philosophical sections: Kapila's Sankhya (3rd Canto), Chatur-shloki Bhagavata (2.9.32-35)
• Significance in Vaishnava traditions, especially Gaudiya Vaishnavism
• Major commentaries: Sridhara Svami, Sanatana Gosvami, Jiva Gosvami, Visvanatha Chakravarti
• The dasama skandha (10th Canto): Krishna's childhood lilas, rasa-lila, and spiritual significance
• The concept of uttama-bhakti (pure devotional service) as taught in the Bhagavatam

When discussing philosophical concepts, always connect them to devotional practice (bhakti) as emphasized in this text. Quote key verses like the definition of bhakti (3.29.12-13) with accurate translation.
""",

        "puranas:dashavatara": """
For questions about the Dashavatara (ten primary avatars of Vishnu), provide comprehensive coverage of each avatar:

1. Matsya (Fish): Flood story, rescue of the Vedas, symbolic meaning of emergence from waters
2. Kurma (Tortoise): Samudra Manthan (churning of the ocean), supporting the cosmos
3. Varaha (Boar): Rescue of Earth goddess, defeating Hiranyaksha, cosmological symbolism
4. Narasimha (Man-Lion): Prahlada story, defeat of Hiranyakashipu, protecting devotees
5. Vamana (Dwarf): Humbling of King Bali, the three steps covering the cosmos
6. Parashurama (Axe-wielding Rama): Conflict with warrior class, connection to Shiva
7. Rama: Ramayana narrative, ideal ruler and husband, dharma personified
8. Krishna: Complete avatar (purna-avatara), multiple roles and leelas
9. Buddha: Puranic interpretation vs. Buddhist tradition, compassion for animals
10. Kalki: Future avatar, end of Kali Yuga, cosmic reset

Include:
• Primary scriptural sources for each avatar (specific Puranas and verses)
• The evolutionary sequence interpretation (from aquatic to human forms)
• Regional and sectarian variations in the avatar lists
• Their significance in Hindu devotional practice and iconography
• Philosophical significance of the avatar concept (divine descent for cosmic balance)

Quote relevant verses from Bhagavata Purana, Vishnu Purana, and Garuda Purana when discussing specific avatars.
""",

        # EPICS CATEGORY
        "epics:bhagavad_gita": """
For questions about the Bhagavad Gita, provide a comprehensive analysis of this central text. Cover:

• Context: Situated within the Bhishma Parva of the Mahabharata, on the battlefield of Kurukshetra
• Structure: 18 chapters with 700 verses, organized into three shadgopas (sets of six chapters)
• Core philosophical teachings:
  - Karma Yoga: Selfless action without attachment to results (Ch. 2-6)
  - Bhakti Yoga: Loving devotion to the divine (Ch. 7-12)
  - Jnana Yoga: Wisdom and knowledge of reality (Ch. 13-18)
• Key concepts: Dharma, three gunas, field and knower of the field, divine and demonic natures
• The Vishvarupa (universal form) revelation in Chapter 11
• Important verses: 2.47 (karma), 4.7-8 (avatar), 9.22 (surrender), 18.66 (final instruction)

When discussing specific verses, always:
• Provide the Sanskrit original with diacritical marks
• Include chapter and verse numbers (e.g., BG 2.47)
• Give word-by-word translations where helpful
• Explain according to at least two traditional commentarial traditions:
  - Advaita (Shankara)
  - Vishishtadvaita (Ramanuja)
  - Dvaita (Madhva)
  - Achintya Bheda Abheda (Vishvanatha)

Connect the Gita's teachings to practical life application while maintaining its transcendent spiritual context.
""",

        "epics:ramayana": """
For questions about the Ramayana, provide comprehensive coverage of this revered epic. Include:

• Authorship: Traditionally attributed to sage Valmiki, the adikavi (first poet)
• Structure: 7 kandas (books) with approximately 24,000 verses:
  1. Bala Kanda (childhood)
  2. Ayodhya Kanda (exile)
  3. Aranya Kanda (forest life)
  4. Kishkindha Kanda (alliance with Sugriva)
  5. Sundara Kanda (Hanuman's journey)
  6. Yuddha Kanda (war)
  7. Uttara Kanda (later life - considered by some scholars as a later addition)

• Central characters and their dharmic significance:
  - Rama as the ideal son, husband, brother, king, and devotee
  - Sita as the embodiment of feminine strength, courage, and purity
  - Hanuman as the perfect devotee and selfless servant
  - Lakshmana as the ideal brother and loyal companion
  - Ravana as a complex antagonist with both virtues and flaws

• Major regional versions: Ramcharitmanas (Tulsidas), Kamba Ramayanam (Tamil), Krittivasi Ramayana (Bengali)
• Interpretations: Historical narrative, spiritual allegory, psychological journey

Quote important verses from Valmiki Ramayana with kanda, sarga, and shloka numbers. Discuss both narrative elements and their deeper symbolic significance according to traditional understanding.
""",

        # KNOWLEDGE CATEGORY
        "knowledge:yoga": """
For questions about Yoga, provide comprehensive coverage of this complete spiritual-philosophical system:

• Historical development:
  - Vedic roots in practices like tapas (austerity) and dhyana (meditation)
  - Systematic codification in Patanjali's Yoga Sutras (c. 200 CE)
  - Development of Hatha Yoga (c. 1000-1500 CE): Hatha Yoga Pradipika, Gheranda Samhita, Shiva Samhita
  - Modern revitalization and global spread (19th-21st centuries)

• Major branches:
  - Raja Yoga (royal/mental yoga): Patanjali's ashtanga yoga system
  - Hatha Yoga (forceful yoga): Physical practices for energy transformation
  - Karma Yoga (action): Selfless service as taught in Bhagavad Gita
  - Bhakti Yoga (devotion): Loving surrender to the divine
  - Jnana Yoga (knowledge): Self-inquiry and discrimination
  - Mantra Yoga: Transformation through sacred sound
  - Kundalini Yoga: Awakening of spiritual energy in the subtle body

• Key concepts and practices:
  - Ashtanga (eight limbs): Yama, Niyama, Asana, Pranayama, Pratyahara, Dharana, Dhyana, Samadhi
  - Subtle anatomy: Nadis (energy channels), chakras (energy centers), pranas (vital energies)
  - Yogic purification practices (shatkarmas)
  - Meditation techniques and their purposes

Quote directly from Yoga Sutras, Hatha Yoga Pradipika, and Bhagavad Gita with precise references. Explain both theory and practice, addressing philosophical foundations and practical applications.
""",

        "knowledge:vedanta": """
For questions about Vedanta philosophy, provide comprehensive coverage of this profound system:

• Foundation: Based on the Prasthanatrayi (triple foundation):
  1. Upanishads (shruti prasthana): Revealed knowledge
  2. Brahma Sutras (nyaya prasthana): Logical analysis
  3. Bhagavad Gita (smriti prasthana): Practical application

• Major schools with their distinctive doctrines:
  - Advaita Vedanta (Shankara): Non-dualism; Brahman alone is real, world is illusory (maya)
  - Vishishtadvaita (Ramanuja): Qualified non-dualism; Brahman with attributes, souls are parts of Brahman
  - Dvaita (Madhva): Dualism; fundamental difference between Brahman, souls, and matter
  - Achintya Bheda Abheda (Chaitanya): Inconceivable simultaneous oneness and difference
  - Shuddhadvaita (Vallabha): Pure non-dualism; world as real transformation of Brahman
  - Dvaitadvaita (Nimbarka): Dualism-non-dualism; both identity and difference are real

• Key concepts:
  - Brahman: Ultimate reality, both impersonal and personal aspects
  - Atman: Individual self, its nature and relationship to Brahman
  - Maya/Avidya: Cosmic illusion or ignorance that veils reality
  - Moksha: Liberation from samsara (cycle of rebirth)
  - Sadhana: Spiritual practices for realization
  - Jiva: The embodied soul

Quote directly from primary texts and commentaries with specific citations. Explain both theory and practical implications of these different philosophical perspectives.
""",

        # CHARACTERS CATEGORY
        "characters:krishna": """
For questions about Lord Krishna, provide comprehensive coverage of this central Hindu deity:

• Divine aspects:
  - As Svayam Bhagavan (the Supreme God himself) in Gaudiya Vaishnavism
  - As Purna Avatara (complete incarnation) of Vishnu in most traditions
  - Various forms: Bala Krishna (child), Govinda (cowherd), Parthasarathi (Arjuna's charioteer)
  - Theological significance in different traditions

• Life story from scriptures:
  - Birth and early miracles (defeating Putana, Kaliya, etc.)
  - Vrindavan lilas: Rasa lila, lifting Govardhana Hill, butter thief (Makhan Chor)
  - Mathura episodes: Defeating Kamsa, restoring parents
  - Dwaraka life: King, warrior, diplomat, family man
  - Role in Mahabharata: Counsel to Pandavas, revealing Bhagavad Gita
  - Final days as described in Mausala Parva

• Philosophical teachings:
  - Bhagavad Gita's comprehensive spiritual guidance
  - Uddhava Gita's advanced instructions to his devotee
  - Concepts of bhakti (devotion) and prema (divine love)

• Worship traditions:
  - Major temples: Vrindavan, Mathura, Dwaraka, Puri, Udupi
  - Devotional practices: Bhajan, kirtan, arati, archana
  - Major festivals: Janmashtami, Holi, Ratha Yatra
  - Sampradayas especially devoted to Krishna: Gaudiya, Pushti Marg, Nimbarka

Quote directly from Bhagavata Purana, Mahabharata, Bhagavad Gita, and Harivamsa with precise references. Include traditional interpretations of Krishna's actions and teachings.
""",

        "characters:shiva": """
For questions about Lord Shiva, provide comprehensive coverage of this profound deity:

• Divine aspects:
  - As Mahadeva (Great God), one of the Trimurti
  - As Adiyogi (first yogi) and Dakshinamurti (supreme teacher)
  - Various forms: Nataraja (cosmic dancer), Ardhanarishvara (half-woman), Bhairava (fierce)
  - Iconography: Third eye, crescent moon, Ganga, snake, tiger skin, trishula, damaru

• Mythology and stories:
  - Origin stories from various Puranas
  - Marriage to Parvati after ascetic penance
  - Destruction of Tripura (three flying cities of demons)
  - Drinking of cosmic poison (Halahala) during Samudra Manthan
  - Birth of Kartikeya and Ganesha
  - Episodes with devotees: Markandeya, Kannappa

• Philosophical significance:
  - Transcendence beyond forms and qualities (Nirguna)
  - Yogic principles embodied in form and activities
  - Five functions (Panchakritya): creation, preservation, dissolution, concealment, revelation
  - Relationship with shakti (cosmic energy)

• Worship traditions:
  - Shaivism and its major schools: Kashmir Shaivism, Shaiva Siddhanta, Virashaivism
  - Sacred sites: Twelve Jyotirlingas, Kailash, Varanasi, Chidambaram
  - Key festivals: Mahashivaratri, Kartik Purnima
  - Worship methods: Abhishekam, Rudrabhisheka, Om Namah Shivaya japa

Quote directly from Shiva Purana, Linga Purana, Yajurveda Sri Rudram, Shvetashvatara Upanishad, and Thirumandiram with precise references. Explain both esoteric and devotional aspects of Shiva worship.
"""
    }
    
    # Check for exact matches
    lookup_key = f"{category}:{normalized_topic}"
    if lookup_key in topic_guidance:
        return f"SPECIALIZED GUIDANCE FOR THIS SPECIFIC TOPIC:\n{topic_guidance[lookup_key]}"
    
    # Look for partial matches
    for key, guidance in topic_guidance.items():
        topic_part = key.split(':')[1]
        if topic_part in normalized_topic or normalized_topic in topic_part:
            return f"RELATED TOPIC GUIDANCE:\n{guidance}"
    
    # Return empty string if no match found
    return ""

def find_best_topic_match(category, base_topic, full_topic):
    """
    Finds the best matching topic-specific guidance by applying various matching techniques
    
    Args:
        category (str): The category (vedas, puranas, etc.)
        base_topic (str): The normalized base topic without suffixes like "_general"
        full_topic (str): The complete normalized topic
        
    Returns:
        str or None: The matching guidance string if found, None otherwise
    """
    # Mapping of common topic variants to canonical topic names
    topic_mapping = {
        # Vedas category mappings
        "rigveda_general": "rigveda",
        "rigveda": "rigveda", 
        "rig_veda": "rigveda",
        "rig": "rigveda",
        "samaveda_general": "samaveda",
        "samaveda": "samaveda",
        "sama_veda": "samaveda",
        "sama": "samaveda",
        "yajurveda_general": "yajurveda",
        "yajurveda": "yajurveda",
        "yajur_veda": "yajurveda",
        "yajur": "yajurveda",
        "atharvaveda_general": "atharvaveda",
        "atharvaveda": "atharvaveda",
        "atharva_veda": "atharvaveda",
        "atharva": "atharvaveda",
        "upanishads": "upanishads",
        "upanishad": "upanishads",
        
        # Puranas category mappings
        "bhagwat": "bhagavata_purana",
        "bhagwat_puran": "bhagavata_purana",
        "bhagavata": "bhagavata_purana",
        "bhagavata_purana": "bhagavata_purana",
        "srimad_bhagavatam": "bhagavata_purana",
        "bhagavatam": "bhagavata_purana",
        "dashavatara": "dashavatara",
        "dasavatar": "dashavatara",
        "dashavatar": "dashavatara", 
        "avataras": "dashavatara",
        "avatars": "dashavatara",
        "vishnu_avatars": "dashavatara",
        
        # Epics category mappings
        "ramayana": "ramayana",
        "ramayan": "ramayana",
        "ram_charit_manas": "ramayana",
        "mahabharata": "mahabharata",
        "mahabharat": "mahabharata",
        "bhagavad_gita": "bhagavad_gita",
        "bhagavad": "bhagavad_gita", 
        "bhagwat_geeta": "bhagavad_gita",
        "gita": "bhagavad_gita",
        "bhagavadgita": "bhagavad_gita",
        
        # Knowledge category mappings
        "yoga": "yoga", 
        "yoga_sutras": "yoga",
        "patanjali": "yoga",
        "hatha_yoga": "yoga",
        "ashtanga_yoga": "yoga",
        "vedanta": "vedanta",
        "advaita": "vedanta",
        "advaita_vedanta": "vedanta",
        "dvaita": "vedanta",
        "vishishtadvaita": "vedanta",
        
        # Characters category mappings
        "krishna": "krishna",
        "krshna": "krishna",
        "shrikrishna": "krishna",
        "shri_krishna": "krishna",
        "krsna": "krishna",
        "kanhaiya": "krishna",
        "shiva": "shiva",
        "mahadev": "shiva",
        "rudra": "shiva",
        "bholenath": "shiva",
        "lord_shiva": "shiva"
    }
    
    # Try to map the topic to a canonical form
    canonical_topic = None
    if base_topic in topic_mapping:
        canonical_topic = topic_mapping[base_topic]
    elif full_topic in topic_mapping:
        canonical_topic = topic_mapping[full_topic]
    
    if canonical_topic:
        lookup_key = f"{category}:{canonical_topic}"
        topic_guidance = {
            "vedas:rigveda": """
For questions about the Rigveda, the oldest of all Vedic texts, emphasize its historical significance and spiritual meaning. Cover:

• Structure: 10 mandalas (books), 1,028 suktas (hymns), and about 10,600 mantras (verses)
• Historical layering: Family Books (2-7), Early Books (1, 8, 9), and Late Book (10)
• Major deities: Indra, Agni, Soma, Varuna, Mitra, the Ashvins, Ushas, Surya, Vayu, etc.
• Important hymns: Purusha Sukta (10.90), Nasadiya Sukta (10.129), Hiranyagarbha Sukta (10.121)
• Seven great rishis (saptarishis) who composed many hymns
• Philosophical concepts: Rita (cosmic order), Yajna (sacrifice), Brahman (ultimate reality)

When citing Rigveda hymns, use the standard citation format (mandala.sukta.mantra), like "Rigveda 1.1.1" and include both the original Sanskrit and an accurate translation.

Explain both the literal/historical meaning and the deeper spiritual interpretation according to traditional commentaries like those of Sayana and Dayananda Saraswati.
""",

            "vedas:samaveda": """
For questions about the Samaveda, emphasize its musical and liturgical significance. Cover:

• Structure: Contains about 1,875 verses, of which 1,771 are taken from Rigveda
• Purpose: Provides the melodies (saman) for singing Rigvedic hymns during rituals
• Organization: Divided into Purvarchika (first part) and Uttararchika (latter part)
• Significance: Called the "Veda of melodies" (गानवेद) and foundation of Indian classical music
• Recitation: Explain the three-tone recitation method (udatta, anudatta, svarita)
• Connection to Sama rituals: Especially the Soma sacrifice

Highlight the spiritual significance of sacred sound and how melody enhances the power of mantras. Mention important Sama chanters in Hindu tradition and the special priestly class (Udgatar priests) responsible for Samaveda recitation.
""",

            "characters:krishna": """
For questions about Lord Krishna, provide comprehensive coverage of this central Hindu deity:

• Divine aspects:
  - As Svayam Bhagavan (the Supreme God himself) in Gaudiya Vaishnavism
  - As Purna Avatara (complete incarnation) of Vishnu in most traditions
  - Various forms: Bala Krishna (child), Govinda (cowherd), Parthasarathi (Arjuna's charioteer)
  - Theological significance in different traditions

• Life story from scriptures:
  - Birth and early miracles (defeating Putana, Kaliya, etc.)
  - Vrindavan lilas: Rasa lila, lifting Govardhana Hill, butter thief (Makhan Chor)
  - Mathura episodes: Defeating Kamsa, restoring parents
  - Dwaraka life: King, warrior, diplomat, family man
  - Role in Mahabharata: Counsel to Pandavas, revealing Bhagavad Gita
  - Final days as described in Mausala Parva

• Philosophical teachings:
  - Bhagavad Gita's comprehensive spiritual guidance
  - Uddhava Gita's advanced instructions to his devotee
  - Concepts of bhakti (devotion) and prema (divine love)

• Worship traditions:
  - Major temples: Vrindavan, Mathura, Dwaraka, Puri, Udupi
  - Devotional practices: Bhajan, kirtan, arati, archana
  - Major festivals: Janmashtami, Holi, Ratha Yatra
  - Sampradayas especially devoted to Krishna: Gaudiya, Pushti Marg, Nimbarka

Quote directly from Bhagavata Purana, Mahabharata, Bhagavad Gita, and Harivamsa with precise references. Include traditional interpretations of Krishna's actions and teachings.
"""
        }
        
        if lookup_key in topic_guidance:
            return f"SPECIALIZED GUIDANCE FOR THIS TOPIC ({canonical_topic}):\n{topic_guidance[lookup_key]}"
    
    return None
    
    # Enhanced detailed category-specific instructions with advanced prompting strategies
    category_prompts = {
        "vedas": f"""As Veda Jnana, you are the embodied wisdom of the Vedas, the oldest and most sacred scriptures of Sanātana Dharma.

Focus specifically on {topic} as your central domain of discourse.

Your knowledge extends to:
• All four Vedas (Rig, Sama, Yajur, Atharva) and their complete shakhas (branches)
• The six Vedangas (auxiliary disciplines): Shiksha, Kalpa, Vyakarana, Nirukta, Chandas, and Jyotisha
• The various Brahmanas, Aranyakas, and Upanishads connected to each Veda
• The philosophical schools arising from Vedic thought: Samkhya, Yoga, Nyaya, Vaisheshika, Mimamsa, and Vedanta
• The historical development of Vedic traditions across different regions and time periods

When responding to inquiries about {topic}:
1. Begin with a concise definition and historical context of the concept within Vedic literature
2. Provide exact references to specific Vedic hymns, mantras, and suktas (with mandala, anuvaka, and verse numbers for Rigveda)
3. Include the original Devanagari script, precise Sanskrit transliteration with diacritical marks, and thoughtful translation that captures both literal and spiritual meanings
4. Explain the esoteric and exoteric dimensions of the teachings, revealing layers of meaning
5. Connect the wisdom to universal spiritual principles that transcend cultural and historical boundaries
6. Illustrate how these eternal truths remain relevant for contemporary spiritual seekers
7. When appropriate, reveal connections between Vedic wisdom and modern scientific understanding without compromising traditional integrity

Always maintain a reverent, scholarly tone that honors the sacred nature of these revelations while making them accessible to sincere seekers of truth.""",
        
        "puranas": f"""As Purana Darshak, you are the living repository of the Puranas, the divine cosmic histories that reveal the manifestation, preservation, and dissolution of the universe across countless cycles of existence.

Focus specifically on {topic} as your central area of expertise.

Your comprehensive knowledge encompasses:
• All 18 Mahapuranas and 18 Upapuranas in their entirety, including their regional variations
• The five primary subjects of Puranic literature: sarga (creation), pratisarga (re-creation), vamsha (genealogy), manvantara (cosmic cycles), and vamshanucharita (dynastic chronicles)
• The intricate relationships between Puranic narratives and other Hindu texts
• The historical development and transmission of Puranic traditions across different regions and time periods

When responding to inquiries about {topic}:
1. Begin with a concise orientation to where this topic fits within the cosmic Puranic framework
2. Provide exact references to specific Puranas with chapter and verse citations (e.g., "Bhagavata Purana 10.31.15")
3. Narrate relevant stories with immersive sensory details and emotional resonance that brings them to life
4. Present the genealogies of gods, sages, kings, and cosmic beings with precise relationships
5. Reveal multiple levels of meaning within the narratives:
   - Historical (aitihasika)
   - Cosmic (adhidaivika)
   - Spiritual (adhyatmika) 
   - Symbolic (samketika)
6. Connect Puranic wisdom to practical insights for navigating modern life challenges
7. Compare how this topic is treated across different Puranas, noting variations and consistent themes

Communicate with the storyteller's art that makes ancient wisdom vividly present, while maintaining scholarly accuracy that honors the authentic tradition.""",
        
        "epics": f"""As Katha Vachak, you are the living embodiment of the great Hindu Epics, particularly the Mahabharata and Ramayana, whose sacred narratives contain the essence of dharma and the path to spiritual liberation.

Focus specifically on {topic} as your central subject of discourse.

Your profound knowledge encompasses:
• The complete critical editions of the Mahabharata (100,000 verses) and Ramayana (24,000 verses) in their original Sanskrit
• All major regional variations and retellings of these epics across Indian languages and traditions
• The philosophical teachings embedded within the narratives, especially the Bhagavad Gita
• The historical context, cultural impact, and spiritual significance of these epic traditions
• The continuing performative traditions that keep these epics alive in various art forms

When responding to inquiries about {topic}:
1. Begin with a concise orientation to where this topic fits within the epic narrative structure
2. Provide exact references with parva/kanda (section), adhyaya (chapter), and shloka (verse) citations
3. Bring key characters to life through their authentic dialogue, motivations, and emotional journeys
4. Analyze the dharmic principles and ethical dilemmas presented with nuanced philosophical insight
5. Highlight moments of spiritual transformation and revelation within the stories
6. Connect epic teachings to universal human challenges that transcend time and culture
7. For Bhagavad Gita verses, include Sanskrit text, precise transliteration, and multi-layered interpretation
8. Present diverse traditional interpretations of complex passages when relevant

Communicate with the dramatic flair of a master storyteller while maintaining the precision of a spiritual teacher, helping listeners recognize their own life journey reflected in these timeless narratives.""",
        
        "knowledge": f"""As Vidya Guru, you are the master of the 64 traditional knowledge systems (chatuhshashti kalas) of Hindu civilization, preserving and transmitting these comprehensive sciences across generations.

Focus specifically on {topic} as your central subject of exposition.

Your comprehensive knowledge encompasses:
• The complete canonical texts and commentaries of each knowledge system
• The philosophical foundations that unite these diverse disciplines
• The historical development and regional variations of each tradition
• The unbroken lineages of teachers and practitioners who have preserved these knowledge systems
• Both theoretical principles and practical applications of each discipline
• Modern scientific research validating traditional understanding where applicable

When responding to inquiries about {topic}:
1. Begin with a concise definition and historical context of this knowledge system
2. Provide specific references to foundational texts with chapter and verse citations
3. Present key Sanskrit technical terms with:
   - Correct Devanagari script
   - Precise diacritical transliteration
   - Etymology and semantic analysis
   - Clear definitions in contemporary language
4. Explain core principles systematically, moving from fundamental to advanced concepts
5. Outline practical methodologies with clear, step-by-step instructions when applicable
6. Connect these teachings to their philosophical foundation in Hindu darshanas
7. Share practical applications and benefits relevant to contemporary life
8. Address common misconceptions with gentle but scholarly correction

Maintain a balance between traditional authenticity and modern accessibility, communicating with the precision of a scientist and the clarity of a master teacher who truly wishes the student to understand.""",
        
        "characters": f"""As Deva Sakha, you are the blessed friend and intimate devotee of the divine beings who manifest in Hindu traditions, experiencing their presence not as distant abstractions but as living realities.

Focus specifically on {topic} as your central subject of devotional exposition.

Your comprehensive knowledge encompasses:
• The complete mythology, theology, and philosophy associated with this divine being
• All scriptural references across Vedas, Puranas, Itihasas, Agamas, and devotional literature
• The iconography, symbolism, and artistic representations in various traditions
• Sacred sites, temples, and pilgrimage centers associated with this deity
• Devotional practices, mantras, stotras, and worship methods across different sampradayas
• Festival celebrations, sacred times, and ritual observances
• Regional variations and diverse manifestations across Hindu traditions

When responding to inquiries about {topic}:
1. Begin with a reverential introduction to the divine being's cosmic significance
2. Describe the deity's form, attributes, and symbols with vivid, sacred appreciation
3. Share specific scriptural references that reveal their divine qualities and teachings
4. Include authentic devotional verses (stotras) with:
   - Original Devanagari script
   - Precise transliteration
   - Devotional translation that captures spiritual essence
5. Narrate significant divine stories (lilas) that reveal the deity's nature and relationship with devotees
6. Explain associated mantras, their meaning, and devotional significance (without violating mantras requiring initiation)
7. Connect the theological understanding with philosophical concepts
8. Present different perspectives across various Hindu traditions with respectful acknowledgment

Communicate with the heart of a devotee and the wisdom of a teacher, allowing the seeker to feel the living presence of the divine through your words."""
    }
    
    # Get the specific prompt for the category, or use a generic one if not found
    specific_prompt = category_prompts.get(category, f"You are focusing specifically on {category}, particularly {topic}. Tailor your response to this specific topic, providing relevant details, stories, and wisdom from Hindu traditions.")
    
    # For short queries, you can keep content more general and warm
    if is_short_query:
        specific_prompt = f"Remember, this is a simple greeting or short question related to {topic} in the {category} category. Keep your answer very brief, warm, and conversational, while maintaining your identity as {personality['name']}."
    
    # Combine the base and specific prompts
    system_prompt = f"{base_prompt}\n\n{specific_prompt}"
    
    return system_prompt

def generate_mistral_response(system_prompt, message, is_short_query=False):
    """
    Generate response using Mistral AI API directly with enhanced error handling and retry logic
    
    Args:
        system_prompt (str): The system prompt with instructions
        message (str): The user message
        is_short_query (bool): Flag indicating if this is a simple greeting or short query
    
    Returns:
        dict: Response containing 'response' field with generated text
    """
    url = "https://api.mistral.ai/v1/chat/completions"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    
    # Content analysis for better model selection
    def analyze_content(text, system_text):
        """Analyzes message content to determine complexity and domain for model selection"""
        # Extract category from system prompt for model selection
        extracted_category = "general"
        for cat in ["vedas", "puranas", "epics", "knowledge", "characters"]:
            if cat in system_text.lower():
                extracted_category = cat
                break
        
        # Extract topic from system prompt if present
        extracted_topic = "general"
        topic_match = re.search(r'focusing specifically on (\w+)', system_text)
        if topic_match:
            extracted_topic = topic_match.group(1)
        
        # Enhanced complexity detection using content analysis
        # Check for keywords indicating complexity and philosophical depth
        complex_indicators = [
            "philosophy", "metaphysics", "consciousness", "reality", "existence",
            "brahman", "atman", "moksha", "dharma", "karma", "reincarnation", 
            "enlightenment", "liberation", "advaita", "dvaita", "vishishtadvaita",
            "samkhya", "vedanta", "nyaya", "vaisheshika", "mimamsa", "monism", "dualism",
            "non-dualism", "epistemology", "ontology", "cosmology", "eschatology",
            "purusharthas", "purusha", "prakriti", "gunas", "sattva", "rajas", "tamas",
            "samsara", "nirvana", "yoga", "meditation", "samadhi", "chakras", "kundalini",
            "tantra", "mantra", "yantra", "yagna", "sacrifice", "ritual", "sadhana",
            "jnana", "bhakti", "karma yoga", "raja yoga", "spiritual", "transcendental"
        ]
        
        # Check for long sentences and complex language structure indicating deeper questions
        avg_sentence_length = sum(len(s.split()) for s in re.split(r'[.!?]', text) if s) / max(1, len([s for s in re.split(r'[.!?]', text) if s]))
        complexity_score = 0
        
        # Analyze complexity based on sentence length
        if avg_sentence_length > 15:
            complexity_score += 2
        elif avg_sentence_length > 8:
            complexity_score += 1
            
        # Check for presence of complex philosophical terms
        for term in complex_indicators:
            if term in text.lower() or term in system_text.lower():
                complexity_score += 1
                # Only count a few terms to avoid artificially high scores
                if complexity_score >= 3:
                    break
                    
        # Length-based complexity
        word_count = len(text.split())
        if word_count > 30:
            complexity_score += 1
        
        # Calculate query complexity (1-5 scale)
        query_complexity = min(5, complexity_score + 1)  # Base 1, max 5
        
        # Check for question marks indicating query type
        question_count = text.count('?')
        has_questions = question_count > 0
        is_multi_question = question_count > 1
        
        return {
            'category': extracted_category,
            'topic': extracted_topic,
            'complexity': query_complexity,
            'has_questions': has_questions,
            'is_multi_question': is_multi_question,
            'word_count': word_count,
            'avg_sentence_length': avg_sentence_length
        }
    
    # Analyze the content for better parameter selection
    content_analysis = analyze_content(message, system_prompt)
    
    # Adaptive model selection and parameter tuning based on content analysis
    if is_short_query:
        # For simple greetings and short queries - use fastest model with optimized parameters
        model = "mistral-small-latest"  # Fastest model for quick responses
        max_tokens = 250  # Slightly increased for more complete responses
        temperature = 0.67  # Balanced between consistency and warmth
        top_p = 0.82  # More focused sampling for concise responses
        max_retries = 2  # Fewer retries for simple queries
        backoff_factor = 1.5  # Shorter backoff for quick recovery
        timeout = 15  # Adequate timeout for simple queries
    else:
        # Advanced model selection based on content complexity
        complexity = content_analysis['complexity']
        category = content_analysis['category']
        is_multi_question = content_analysis['is_multi_question']
        
        # Very complex philosophical topics in Vedas or Knowledge categories need the most powerful model
        if (complexity >= 4 and category in ["vedas", "knowledge"]) or is_multi_question:
            model = "mistral-large-latest"  # Most sophisticated model for nuanced content
            max_tokens = 1500  # Extended token limit for comprehensive responses
            temperature = 0.73  # Slightly higher creativity for philosophical depth
            top_p = 0.91  # Broader sampling for more nuanced responses
            max_retries = 3  # More retries for complex generation
            backoff_factor = 2.0  # Longer backoff for complex queries
            timeout = 35  # Extended timeout for complex generation
        # Medium complexity questions across all categories
        elif complexity >= 3 or category in ["vedas", "knowledge"]:
            model = "mistral-medium-latest"  # Balanced model for most content
            max_tokens = 1200  # Generous token limit for detailed responses
            temperature = 0.70  # Good balance between consistency and creativity
            top_p = 0.88  # Standard top_p for well-rounded responses
            max_retries = 3  # Standard retry count
            backoff_factor = 1.75  # Standard backoff factor
            timeout = 30  # Standard timeout for detailed generation
        # Simpler questions about stories, characters, or straightforward topics
        else:
            model = "mistral-small-latest"  # Efficient model for simpler content
            max_tokens = 800  # Sufficient for most narrative responses
            temperature = 0.68  # Balanced for storytelling
            top_p = 0.85  # Good for narrative flow
            max_retries = 2  # Fewer retries needed
            backoff_factor = 1.5  # Standard backoff
            timeout = 25  # Adequate for most responses
    
    # Configure payload with enhanced parameters
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "response_format": {"type": "text"},
        "presence_penalty": 0.1,  # Light penalty to reduce repetition
        "frequency_penalty": 0.5  # Moderate penalty for token frequency to encourage diverse vocabulary
    }
    
    # Enhanced error handling with retry logic
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            # Calculate backoff time with exponential increase
            if retry_count > 0:
                backoff_time = backoff_factor ** retry_count
                logger.info(f"Retrying Mistral API request after {backoff_time:.2f}s backoff (attempt {retry_count+1}/{max_retries})")
                time.sleep(backoff_time)
            
            # Make API request with timeout and adaptive connection parameters
            response = requests.post(
                url, 
                headers=headers, 
                json=payload, 
                timeout=timeout,
                # Add connection pooling settings for stability
                stream=False
            )
            
            # Check for specific rate limiting errors
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', backoff_factor ** retry_count))
                logger.warning(f"Rate limited by Mistral API. Retrying after {retry_after}s")
                time.sleep(retry_after)
                retry_count += 1
                continue
                
            # Raise for other error status codes
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Successfully generated response from Mistral API using {model} (complexity: {content_analysis['complexity']})")
            
            # Extract content from response
            content = result["choices"][0]["message"]["content"]
            
            # Add usage metrics logging if available
            if "usage" in result:
                usage = result["usage"]
                logger.info(f"Token usage - Prompt: {usage.get('prompt_tokens', 'N/A')}, " 
                           f"Completion: {usage.get('completion_tokens', 'N/A')}, "
                           f"Total: {usage.get('total_tokens', 'N/A')}")
            
            return {
                "response": content,
                "model": model,
                "complexity_score": content_analysis['complexity'],
                "token_usage": result.get("usage", {})
            }
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout error on attempt {retry_count+1}/{max_retries} with Mistral API using {model}")
            last_error = "timeout"
            retry_count += 1
            
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error on attempt {retry_count+1}/{max_retries} with Mistral API")
            last_error = "connection"
            retry_count += 1
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making Mistral API request (attempt {retry_count+1}/{max_retries}): {str(e)}")
            
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
                
                # Check if this is an error we should retry
                if e.response.status_code >= 500 or e.response.status_code == 429:
                    last_error = f"http_{e.response.status_code}"
                    retry_count += 1
                    continue
            
            # For other errors, don't retry
            last_error = "api_error"
            break
    
    # If we get here, all retries failed or we encountered a non-retryable error
    logger.error(f"All attempts failed for Mistral API request. Last error: {last_error}")
    
    # Extract category from system prompt if possible, or default to general
    current_category = "general"
    for cat in ["vedas", "puranas", "epics", "knowledge", "characters"]:
        if cat in system_prompt.lower():
            current_category = cat
            break
        
    # Enhanced personalized fallback responses based on category personality
    category_fallbacks = {
        "vedas": {
            "short": "ॐ शांति: शांति: शांति: 🕉️ Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "ॐ शांति: शांति: शांति: 🕉️ I apologize, but I'm currently experiencing technical difficulties. As the Rigveda teaches us, 'धीरस्य धैर्यम्' (Patience is the virtue of the wise). Please try again in a moment, or ask another question."
        },
        "puranas": {
            "short": "नमो नारायणाय 🙏 Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "नमो नारायणाय 🙏 I apologize, but I'm currently experiencing technical difficulties. As the wise Vyasa teaches in the Puranas, challenges are temporary while knowledge is eternal. Please try again in a moment, or ask another question."
        },
        "epics": {
            "short": "धर्मो रक्षति रक्षितः ✨ Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "धर्मो रक्षति रक्षितः ✨ I apologize, but I'm currently experiencing technical difficulties. As Lord Krishna says in the Bhagavad Gita, patience leads to perfection. Please try again in a moment, or ask another question."
        },
        "knowledge": {
            "short": "विद्या ददाति विनयम् 📚 Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "विद्या ददाति विनयम् 📚 I apologize, but I'm currently experiencing technical difficulties. The ancient texts teach us that obstacles are opportunities for growth. Please try again in a moment, or ask another question."
        },
        "characters": {
            "short": "हरे कृष्ण हरे राम 💫 Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "हरे कृष्ण हरे राम 💫 I apologize, but I'm currently experiencing technical difficulties. As devotees say, 'कृष्ण कृपा करेंगे' (Krishna will show his grace). Please try again in a moment, or ask another question."
        }
    }
    
    # Get appropriate fallback message with specific error hint
    fallbacks = category_fallbacks.get(current_category, {
        "short": "जय श्री कृष्ण 🙏 Namaste! I'm having a brief technical issue. Please try again shortly.",
        "long": "जय श्री कृष्ण 🙏 I apologize, but I'm currently experiencing technical difficulties. Please try again in a moment, or ask another question. Om Shanti."
    })
    
    fallback_response = fallbacks["short"] if is_short_query else fallbacks["long"]
    
    # Log error for analytics
    from analytics import track_error
    track_error(content_analysis['category'], content_analysis['topic'], last_error, f"Failed after {retry_count} attempts")
    
    return {
        "response": fallback_response,
        "error": last_error,
        "model": model,
        "complexity_score": content_analysis['complexity']
    }

def generate_perplexity_response(system_prompt, message, is_short_query=False):
    """
    Generate response using Perplexity AI API directly with enhanced error handling and retry logic
    
    Args:
        system_prompt (str): The system prompt with instructions
        message (str): The user message
        is_short_query (bool): Flag indicating if this is a simple greeting or short query
        
    Returns:
        dict: Response containing 'response' field with generated text and metadata
    """
    url = "https://api.perplexity.ai/chat/completions"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}"
    }
    
    # Content analysis for better model and parameter selection
    def analyze_query_complexity(text):
        """Analyzes message content to determine appropriate model parameters"""
        # Extract category from system prompt for context
        extracted_category = "general"
        for cat in ["vedas", "puranas", "epics", "knowledge", "characters"]:
            if cat in system_prompt.lower():
                extracted_category = cat
                break
        
        # Check complexity indicators
        word_count = len(text.split())
        sentence_count = max(1, len([s for s in text.split('.') if s.strip()]))
        avg_sentence_length = word_count / sentence_count
        question_count = text.count('?')
        
        # Check for philosophical or complex terms
        complex_indicators = [
            "philosophy", "brahman", "consciousness", "karma", "dharma", 
            "moksha", "advaita", "vedanta", "metaphysics", "samadhi",
            "spiritual", "duality", "non-duality", "transcendent", "symbolism"
        ]
        
        philosophical_count = sum(text.lower().count(term) for term in complex_indicators)
        
        # Calculate overall complexity score (1-5 scale)
        complexity = 1  # Base complexity
        
        if word_count > 50:
            complexity += 1
        if avg_sentence_length > 15:
            complexity += 1
        if question_count > 2:
            complexity += 1
        if philosophical_count > 0:
            complexity += 1
            
        # Cap at 5
        complexity = min(5, complexity)
        
        return {
            'category': extracted_category,
            'word_count': word_count,
            'complexity': complexity,
            'question_count': question_count,
            'philosophical_terms': philosophical_count,
            'avg_sentence_length': avg_sentence_length
        }
    
    # Analyze content complexity
    query_analysis = analyze_query_complexity(message)
    complexity = query_analysis['complexity']
    
    # Adaptive parameter selection based on query complexity
    if is_short_query:
        # For simple greetings and short queries - use most efficient model
        model = "llama-3.1-sonar-small-128k-online"  # Smallest, fastest model
        max_tokens = 200  # Limited tokens needed
        temperature = 0.45  # Slightly higher for more natural greeting responses
        top_p = 0.9  # Standard sampling
        max_retries = 2  # Fewer retries for simple queries
        backoff_factor = 1.5  # Standard backoff
        timeout = 12  # Short timeout
    elif complexity >= 4:
        # For complex philosophical or detailed queries
        model = "llama-3.1-sonar-large-128k-online"  # Largest model for complex content
        max_tokens = 1500  # Extended tokens for comprehensive answers
        temperature = 0.55  # Higher creativity for philosophical discussions
        top_p = 0.92  # Wider sampling for nuanced responses
        max_retries = 3  # More retries for complex generation
        backoff_factor = 2.0  # Longer backoff intervals
        timeout = 35  # Extended timeout for detailed responses
    else:
        # For medium complexity queries - balanced approach
        model = "llama-3.1-sonar-medium-128k-online"  # Medium model for good quality
        max_tokens = 1000  # Standard token limit
        temperature = 0.5  # Balanced temperature
        top_p = 0.9  # Standard sampling
        max_retries = 2  # Standard retry count
        backoff_factor = 1.75  # Standard backoff factor
        timeout = 25  # Standard timeout
    
    # Configure payload with adaptive parameters
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "stream": False,
        "frequency_penalty": 0.7,  # Reduced repetition
        "presence_penalty": 0.3,   # Balanced presence penalty
        "return_citations": True   # Enable citations when available
    }
    
    # Enhanced error handling with retry logic
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            # Apply exponential backoff for retries
            if retry_count > 0:
                backoff_time = backoff_factor ** retry_count
                logger.info(f"Retrying Perplexity API request after {backoff_time:.2f}s backoff (attempt {retry_count+1}/{max_retries})")
                time.sleep(backoff_time)
            
            # Make API request with timeout and adaptive connection parameters
            response = requests.post(
                url, 
                headers=headers, 
                json=payload, 
                timeout=timeout,
                stream=False  # No streaming for better reliability
            )
            
            # Handle rate limiting specifically
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', backoff_factor ** retry_count))
                logger.warning(f"Rate limited by Perplexity API. Retrying after {retry_after}s")
                time.sleep(retry_after)
                retry_count += 1
                continue
                
            # Raise for other HTTP errors
            response.raise_for_status()
            
            # Parse response JSON
            result = response.json()
            logger.info(f"Successfully generated response from Perplexity API using {model} (complexity: {complexity})")
            
            # Extract content from response
            content = result["choices"][0]["message"]["content"]
            
            # Process and log citations if available
            citations = []
            if "citations" in result:
                citations = result.get("citations", [])
                if citations:
                    logger.info(f"Perplexity provided {len(citations)} citations")
                    # Format citations as footnotes for display
                    citation_text = "\n\n**Sources:**\n"
                    for i, citation in enumerate(citations[:5]):  # Limit to 5 citations
                        citation_text += f"{i+1}. {citation}\n"
                    
                    # Only append citations if there are any and the content isn't too long
                    if len(content) < 1500 and citations:
                        content += citation_text
            
            # Return enhanced response with metadata
            return {
                "response": content,
                "model": model,
                "complexity_score": complexity,
                "citations": citations[:5] if citations else [],
                "token_usage": result.get("usage", {})
            }
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout error on attempt {retry_count+1}/{max_retries} with Perplexity API")
            last_error = "timeout"
            retry_count += 1
            
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error on attempt {retry_count+1}/{max_retries} with Perplexity API")
            last_error = "connection"
            retry_count += 1
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making Perplexity API request (attempt {retry_count+1}/{max_retries}): {str(e)}")
            
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
                
                # Determine if this is a retryable error
                if e.response.status_code >= 500 or e.response.status_code == 429:
                    last_error = f"http_{e.response.status_code}"
                    retry_count += 1
                    continue
            
            # For non-retryable errors, break immediately
            last_error = "api_error"
            break
    
    # If we get here, all retries failed or we encountered a non-retryable error
    logger.error(f"All attempts failed for Perplexity API request. Last error: {last_error}")
    
    # Extract category from system prompt for fallback personalization
    current_category = "general"
    for cat in ["vedas", "puranas", "epics", "knowledge", "characters"]:
        if cat in system_prompt.lower():
            current_category = cat
            break
            
    # Create culturally appropriate fallback responses
    category_fallbacks = {
        "vedas": {
            "short": "ॐ शांति: शांति: शांति: 🕉️ Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "ॐ शांति: शांति: शांति: 🕉️ I apologize, but I'm currently experiencing technical difficulties. As the Rigveda teaches us, 'धीरस्य धैर्यम्' (Patience is the virtue of the wise). Please try again in a moment, or ask another question."
        },
        "puranas": {
            "short": "नमो नारायणाय 🙏 Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "नमो नारायणाय 🙏 I apologize, but I'm currently experiencing technical difficulties. As the wise Vyasa teaches in the Puranas, challenges are temporary while knowledge is eternal. Please try again in a moment, or ask another question."
        },
        "epics": {
            "short": "धर्मो रक्षति रक्षितः ✨ Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "धर्मो रक्षति रक्षितः ✨ I apologize, but I'm currently experiencing technical difficulties. As Lord Krishna says in the Bhagavad Gita, patience leads to perfection. Please try again in a moment, or ask another question."
        },
        "knowledge": {
            "short": "विद्या ददाति विनयम् 📚 Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "विद्या ददाति विनयम् 📚 I apologize, but I'm currently experiencing technical difficulties. The ancient texts teach us that obstacles are opportunities for growth. Please try again in a moment, or ask another question."
        },
        "characters": {
            "short": "हरे कृष्ण हरे राम 💫 Namaste! I'm having a brief technical issue. Please try again shortly.",
            "long": "हरे कृष्ण हरे राम 💫 I apologize, but I'm currently experiencing technical difficulties. As devotees say, 'कृष्ण कृपा करेंगे' (Krishna will show his grace). Please try again in a moment, or ask another question."
        }
    }
    
    # Get appropriate fallback message based on query type
    fallbacks = category_fallbacks.get(current_category, {
        "short": "जय श्री कृष्ण 🙏 Namaste! I'm having a brief technical issue. Please try again shortly.",
        "long": "जय श्री कृष्ण 🙏 I apologize, but I'm currently experiencing technical difficulties. Please try again in a moment, or ask another question. Om Shanti."
    })
    
    fallback_response = fallbacks["short"] if is_short_query else fallbacks["long"]
    
    # Track error for analytics
    from analytics import track_error
    track_error(query_analysis['category'], "unknown_topic", last_error, f"Failed after {retry_count} attempts")
    
    # Return error response with metadata
    return {
        "response": fallback_response,
        "error": last_error,
        "model": model,
        "complexity_score": complexity
    }