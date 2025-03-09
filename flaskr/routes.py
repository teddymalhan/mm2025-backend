from flask import Blueprint, request, jsonify
import random
from openai import OpenAI
import yt_dlp

# Initialize OpenAI client
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
client = OpenAI(api_key=OPENAI_API_KEY)

bp = Blueprint('main', __name__)

@bp.route("/")
def home():
    return jsonify(message="Welcome to the Mountain Madness Backend!")

@bp.route("/process", methods=["POST"])
def process():
    data = request.json  # Get JSON data from frontend

    # Extract parameters
    study_topic = data.get("studyTopic")
    duration = data.get("duration", "medium")  # Use "medium" as default
    slider_value = data.get("sliderValue")  # Dummy variable
    random_theme = data.get("randomTheme")

    if not study_topic:
        return jsonify({"error": "No study topic provided"}), 400
    if not random_theme:
        return jsonify({"error": "No random theme provided"}), 400
    
    # Extract keywords using GPT-4
    keywords = get_keywords_from_prompt(study_topic)
    if isinstance(keywords, dict) and "error" in keywords:
        return jsonify(keywords), 500
    
    # Get useful videos from YouTube using the extracted keywords and filter by duration
    useful_videos = get_youtube_videos_for_keywords(keywords, duration=duration)
    
    # Get fun videos using the provided random theme (not checking for Shorts)
    fun_videos = get_youtube_fun_videos(random_theme)
    
    # Interleave fun videos into the useful videos list
    combined_videos = interleave_fun_videos(useful_videos, fun_videos)
    
    return jsonify(combined_videos)

@bp.route("/quiz", methods=["POST"])
def process_quiz():
    data = request.json

    # Extract parameters
    youtube_id = data.get("youtubeId")

    if not youtube_id:
        return jsonify({"error": "No YouTube ID provided"}), 400
    
    # Get quiz questions for the provided YouTube video ID
    subtitles = get_subtitles(youtube_id)

    quiz = create_quiz(subtitles)

    return jsonify(quiz)

# Helper functions
def get_keywords_from_prompt(prompt):
    """
    Uses OpenAI's chat completion API with model 'gpt-4' to generate an ordered lesson plan with YouTube-searchable keywords.
    Ensures that keywords are unique and cover different aspects of the topic.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{
                "role": "user",
                "content": f"""
                Create an **ordered lesson plan** with different keywords that can be searched on YouTube to generate a complete video series lesson plan for the given topic. 

                - **Ensure that each keyword is unique and distinct.**
                - **Do not include repetitive or nearly identical search terms.**
                - **Each keyword should focus on a different concept, application, or technical detail.**
                - **Ensure that the keywords are commonly searched on YouTube and yield different video results.**
                
                **Return the lesson plan as an ordered list in a single string, with each lesson separated by commas.**
                
                ### **Example Format** (for "Machine Learning"):  
                1. Introduction to Machine Learning,  
                2. History and Evolution of Machine Learning,  
                3. Supervised vs. Unsupervised Learning: Key Differences,  
                4. Common Machine Learning Algorithms Explained,  
                5. Feature Engineering and Data Preprocessing,  
                6. Understanding Bias and Variance in Machine Learning,  
                7. Real-World Applications of Machine Learning,  
                8. Explainability and Interpretability in AI,  
                9. Hands-on Machine Learning Project Tutorial,  
                10. Ethical Considerations in Machine Learning.  

                Now generate a lesson plan for this topic: **{prompt}**
                """
            }],
            max_tokens=300,
        )
    except Exception as e:
        return {"error": f"Error in GPT-4 call: {str(e)}"}

    result = response.choices[0].message.content.strip()
    keywords = list(dict.fromkeys([keyword.strip() for keyword in result.split(",") if keyword.strip()]))  # Remove duplicates
    return keywords

def search_youtube_videos(query, max_results=5, duration_filter=None, is_fun=False):
    """
    Uses yt_dlp to search for YouTube videos based on the query.
    Filters based on duration and ensures that fun videos are marked correctly.
    Includes channel name in response.
    """
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,  # Extract metadata without downloading
        "force_generic_extractor": True,
        "default_search": "ytsearch",
        "max_downloads": max_results,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

    videos = []
    seen_titles = set()  # To store unique video titles and prevent duplicates

    for entry in search_results.get("entries", []):
        video_title = entry.get("title")
        video_url = entry.get("url")
        video_channel = entry.get("channel", "Unknown Channel")  # Fetch channel name
        duration = entry.get("duration", 0)  # Duration in seconds

        # **Filter by duration for study videos**
        if not is_fun:  
            if duration_filter == "short" and duration >= 240:  # Less than 4 minutes
                continue
            if duration_filter == "medium" and (duration < 240 or duration > 1200):  # 4-20 minutes
                continue
            if duration_filter == "long" and duration <= 1200:  # More than 20 minutes
                continue

        # **Avoid duplicate titles**
        if video_title in seen_titles:
            continue

        seen_titles.add(video_title)
        videos.append({
            "title": video_title,
            "url": video_url,
            "channel": video_channel,  # Include channel name
            "is_fun": is_fun  # **Set True for fun videos, False for study videos**
        })

    return videos

def get_youtube_fun_videos(fun_topic, max_results=3):
    """
    Uses yt_dlp to search for fun YouTube videos (not necessarily Shorts).
    Always sets is_fun=True.
    """
    return search_youtube_videos(fun_topic, max_results=max_results, is_fun=True)

def get_youtube_videos_for_keywords(keywords, max_results=5, duration="medium"):
    """
    Uses yt_dlp to search for educational videos on YouTube for each keyword, filtered by duration.
    Always sets is_fun=False.
    """
    videos = []
    for keyword in keywords:
        videos.extend(search_youtube_videos(keyword, max_results=max_results, duration_filter=duration, is_fun=False))
    return videos

def interleave_fun_videos(useful_videos, fun_videos):
    """
    Randomly interleaves the fun videos into the useful videos list.
    """
    combined_videos = useful_videos.copy()
    for fun_video in fun_videos:
        insert_index = random.randint(0, len(combined_videos))
        combined_videos.insert(insert_index, fun_video)
    return combined_videos

def get_subtitles(youtube_id, lang='en'):
    """
    Extracts subtitles from a YouTube video using yt_dlp.
    """
    video_url = f"https://www.youtube.com/watch?v={youtube_id}"

    ydl_opts = {
        'writeautomaticsub': True,  # Download auto-generated subtitles
        'subtitleslangs': [lang],   # Language of the subtitles
        'skip_download': True,      # Skip the video download, we only need the subtitles
        'outtmpl': 'subs.txt'       # Template for naming the output file
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    
    with open('subs.txt.en.vtt', 'r') as file:
        subtitles = file.read()
    
    return subtitles

def create_quiz(subtitles):
    """
    Uses OpenAI's chat completion API with model 'gpt-4' to generate quiz questions based on the subtitles.
    Truncates the subtitles to avoid exceeding the token limit.
    """
    # Truncate subtitles to the first 2000 characters to avoid exceeding the token limit
    truncated_subtitles = subtitles[:2000]

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{
                "role": "user",
                "content": f"""make 8 mcq questions based on this youtube transcript and return it as a json file: {truncated_subtitles}. keep the structure like [{{'question', 'answer'}}]"""
            }],
            max_tokens=300,
        )
        result = response.choices[0].message.content.strip()
        return result
    except Exception as e:
        return {"error": f"Error in GPT-4 call: {str(e)}"}