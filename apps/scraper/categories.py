"""Google Play app niches (categories) for the search dropdown.

VALUE -> Play Store genre string as returned by google-play-scraper's
`genre` field. The values here are what Play actually emits, so the
filter compares against the stored App.category unchanged.
"""

from __future__ import annotations

CATEGORIES: list[tuple[str, str]] = [
    ("art_and_design", "Art & Design"),
    ("auto_and_vehicles", "Auto & Vehicles"),
    ("beauty", "Beauty"),
    ("books_and_reference", "Books & Reference"),
    ("business", "Business"),
    ("comics", "Comics"),
    ("communication", "Communication"),
    ("dating", "Dating"),
    ("education", "Education"),
    ("entertainment", "Entertainment"),
    ("events", "Events"),
    ("finance", "Finance"),
    ("food_and_drink", "Food & Drink"),
    ("health_and_fitness", "Health & Fitness"),
    ("house_and_home", "House & Home"),
    ("libraries_and_demo", "Libraries & Demo"),
    ("lifestyle", "Lifestyle"),
    ("maps_and_navigation", "Maps & Navigation"),
    ("medical", "Medical"),
    ("music_and_audio", "Music & Audio"),
    ("news_and_magazines", "News & Magazines"),
    ("parenting", "Parenting"),
    ("personalization", "Personalization"),
    ("photography", "Photography"),
    ("productivity", "Productivity"),
    ("shopping", "Shopping"),
    ("social", "Social"),
    ("sports", "Sports"),
    ("tools", "Tools"),
    ("travel_and_local", "Travel & Local"),
    ("video_players_and_editors", "Video Players & Editors"),
    ("weather", "Weather"),
    ("games", "Games"),
    ("action", "Action"),
    ("adventure", "Adventure"),
    ("arcade", "Arcade"),
    ("board", "Board"),
    ("card", "Card"),
    ("casino", "Casino"),
    ("casual", "Casual"),
    ("educational_games", "Educational"),
    ("music", "Music"),
    ("puzzle", "Puzzle"),
    ("racing", "Racing"),
    ("role_playing", "Role Playing"),
    ("simulation", "Simulation"),
    ("strategy", "Strategy"),
    ("trivia", "Trivia"),
    ("word", "Word"),
]

CATEGORY_LABELS: dict[str, str] = dict(CATEGORIES)


def label_for(value: str) -> str:
    return CATEGORY_LABELS.get(value, value)
