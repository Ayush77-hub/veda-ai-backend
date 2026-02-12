"""
Categories and topics data structure for the Hindu sacred texts chatbots.
This matches the structure used in the frontend for consistent behavior.
"""

# Define the structure of categories, subcategories, and topics
categories = [
  {
    "id": "vedas",
    "name": "Vedas",
    "subcategories": [
      {
        "id": "rigveda",
        "name": "Rigveda",
        "topics": [
          { "id": "rigveda-general", "name": "Rigveda" }
        ]
      },
      {
        "id": "yajurveda",
        "name": "Yajurveda",
        "topics": [
          { "id": "yajurveda-general", "name": "Yajurveda" }
        ]
      },
      {
        "id": "samaveda",
        "name": "Samaveda",
        "topics": [
          { "id": "samaveda-general", "name": "Samaveda" }
        ]
      },
      {
        "id": "atharvaveda",
        "name": "Atharvaveda",
        "topics": [
          { "id": "atharvaveda-general", "name": "Atharvaveda" }
        ]
      }
    ]
  },
  {
    "id": "puranas",
    "name": "Puranas",
    "topics": [
      { "id": "bhagwat", "name": "Bhagwat Puran" },
      { "id": "bhavishya", "name": "Bhavishya Puran" },
      { "id": "brahma", "name": "Brahma Puran" },
      { "id": "brahmand", "name": "Brahmand Puran" },
      { "id": "garuda", "name": "Garuda Puran" },
      { "id": "kurma", "name": "Kurma Puran" },
      { "id": "ling", "name": "Ling Puran" },
      { "id": "markandya", "name": "Markandya Puran" },
      { "id": "matsya", "name": "Matsya Puran" },
      { "id": "narad", "name": "Narad Puran" },
      { "id": "padma", "name": "Padma Puran" },
      { "id": "shiv", "name": "Shiv Puran" },
      { "id": "skand", "name": "Skand Puran" },
      { "id": "brahmvaivatra", "name": "BrahmVaivatra Puran" },
      { "id": "vaman", "name": "Vaman Puran" },
      { "id": "varah", "name": "Varah Puran" },
      { "id": "vishnu", "name": "Vishnu Puran" }
    ]
  },
  {
    "id": "epics",
    "name": "Epics",
    "topics": [
      { "id": "mahabharata", "name": "Mahabharata" },
      { "id": "ramayana", "name": "Ramayana" },
      { "id": "ramcharitmanas", "name": "Ramcharitmanas" },
      { "id": "gita", "name": "Gita" }
    ]
  },
  {
    "id": "knowledge",
    "name": "Knowledge",
    "topics": [
      { "id": "ayurveda", "name": "Ayurveda" },
      { "id": "jyotish", "name": "Jyotish" }
    ]
  },
  {
    "id": "characters",
    "name": "Characters",
    "subcategories": [
      {
        "id": "devas",
        "name": "Devas",
        "topics": [
          { "id": "vishnu", "name": "Lord Vishnu" },
          { "id": "shiva", "name": "Lord Shiva" },
          { "id": "brahma", "name": "Lord Brahma" },
          { "id": "indra", "name": "Lord Indra" },
          { "id": "surya", "name": "Lord Surya" }
        ]
      },
      {
        "id": "avatars",
        "name": "Avatars",
        "topics": [
          { "id": "rama", "name": "Lord Rama" },
          { "id": "krishna", "name": "Lord Krishna" },
          { "id": "narasimha", "name": "Lord Narasimha" },
          { "id": "vamana", "name": "Lord Vamana" },
          { "id": "parashurama", "name": "Lord Parashurama" }
        ]
      },
      {
        "id": "sages",
        "name": "Sages",
        "topics": [
          { "id": "vashishtha", "name": "Sage Vashishtha" },
          { "id": "vishwamitra", "name": "Sage Vishwamitra" },
          { "id": "narada", "name": "Sage Narada" },
          { "id": "vyasa", "name": "Sage Vyasa" },
          { "id": "valmiki", "name": "Sage Valmiki" }
        ]
      }
    ]
  }
]

def get_all_categories():
    """
    Return all categories
    """
    return categories

def get_category_by_id(category_id):
    """
    Find and return a category by its id
    """
    for category in categories:
        if category['id'] == category_id:
            return category
    return None

def get_subcategory_by_id(category_id, subcategory_id):
    """
    Find and return a subcategory by its id within a specific category
    """
    category = get_category_by_id(category_id)
    
    if not category or 'subcategories' not in category:
        return None
        
    for subcategory in category['subcategories']:
        if subcategory['id'] == subcategory_id:
            return subcategory
            
    return None

def get_all_topics():
    """
    Extract and return all topics from all categories and subcategories
    """
    all_topics = []
    
    for category in categories:
        # Add topics from categories
        if 'topics' in category:
            for topic in category['topics']:
                all_topics.append({
                    'id': topic['id'],
                    'name': topic['name'],
                    'category_id': category['id'],
                    'subcategory_id': None
                })
                
        # Add topics from subcategories
        if 'subcategories' in category:
            for subcategory in category['subcategories']:
                if 'topics' in subcategory:
                    for topic in subcategory['topics']:
                        all_topics.append({
                            'id': topic['id'],
                            'name': topic['name'],
                            'category_id': category['id'],
                            'subcategory_id': subcategory['id']
                        })
    
    return all_topics

def get_topic_info(topic_id, category_id=None, subcategory_id=None):
    """
    Find and return topic information by its id, optionally filtering by category and subcategory
    """
    all_topics = get_all_topics()
    
    for topic in all_topics:
        if topic['id'] == topic_id:
            if category_id and topic['category_id'] != category_id:
                continue
                
            if subcategory_id and topic['subcategory_id'] != subcategory_id:
                continue
                
            return topic
            
    return None

def get_category_name(category_id):
    """
    Get category name by id
    """
    category = get_category_by_id(category_id)
    return category['name'] if category else 'Unknown Category'

def get_subcategory_name(category_id, subcategory_id):
    """
    Get subcategory name by id
    """
    subcategory = get_subcategory_by_id(category_id, subcategory_id)
    return subcategory['name'] if subcategory else 'Unknown Subcategory'

def get_topic_name(topic_id):
    """
    Get topic name by id
    """
    all_topics = get_all_topics()
    
    for topic in all_topics:
        if topic['id'] == topic_id:
            return topic['name']
            
    return 'Unknown Topic'