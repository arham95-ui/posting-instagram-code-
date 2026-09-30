import cv2
import time
import json
import threading
from datetime import datetime
from pathlib import Path

from ultralytics import YOLO

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    RateLimitError,
    ClientError,
    ChallengeRequired,
    TwoFactorRequired
)
from instagrapi.mixins.challenge import ChallengeChoice


# ============================================================
# FLUSH STDOUT FOR REAL-TIME LOGGING
# ============================================================

_print = print


def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _print(*args, **kwargs)


# ============================================================
# SETTINGS & CONFIGURATION
# ============================================================

CAMERA_INDEX = 0

# Number of consecutive frames required before capture
REQUIRED_FRAMES = 5

# Prevent repeated captures
CAPTURE_COOLDOWN = 8

# YOLO settings
YOLO_CONFIDENCE = 0.30
YOLO_IMAGE_SIZE = 640

# ------------------------------------------------------------
# PALM VIDEO SETTINGS
# ------------------------------------------------------------
PALM_VIDEO_DURATION = 5
PALM_VIDEO_FPS = 20.0
PALM_VIDEO_COOLDOWN = 8

# ============================================================
# LOCAL IMAGE FRAME
# FREE - NO GEMINI
# ============================================================

FRAME_BRAND_NAME = "AI SOFT Faisalabad"

FRAME_BORDER = 35
FRAME_TOP_SPACE = 95
FRAME_BOTTOM_SPACE = 75


# ============================================================
# INSTAGRAM ACCOUNT
# ============================================================

USERNAME = ""
PASSWORD = ""


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).parent.resolve()

SAVE_DIR = BASE_DIR / "captured_images"
SAVE_DIR.mkdir(exist_ok=True)

SESSION_FILE = BASE_DIR / "session.json"
HISTORY_FILE = BASE_DIR / "posted_history.json"

# YOLO model
MODEL_FILE = BASE_DIR / "yolo26n_hand-gesture_12c_v1.pt"


# ============================================================
# INSTAGRAM SESSION & CLIENT MANAGEMENT
# ============================================================

def challenge_code_handler(username, choice):

    print()
    print("=" * 60)
    print(
        f"[!] INSTAGRAM SECURITY VERIFICATION REQUIRED "
        f"for @{username}"
    )

    if choice == ChallengeChoice.SMS:

        print(
            "[!] A verification code was sent "
            "to your phone via SMS."
        )

    elif choice == ChallengeChoice.EMAIL:

        print(
            "[!] A verification code was sent "
            "to your EMAIL address."
        )

    else:

        print(
            f"[!] Verification required "
            f"(Choice: {choice})."
        )

    print("=" * 60)

    return input(
        "--> Enter the verification code here: "
    ).strip()


def create_fresh_client():

    cl = Client()

    cl.challenge_code_handler = challenge_code_handler

    cl.delay_range = [2, 5]

    return cl


def get_instagram_client(force_new=False):

    session_path = Path(SESSION_FILE)

    # --------------------------------------------------------
    # LOAD EXISTING SESSION
    # --------------------------------------------------------

    if not force_new and session_path.exists():

        try:

            print(
                f"[+] Loading cached session from "
                f"{SESSION_FILE.name}..."
            )

            cl = create_fresh_client()

            cl.load_settings(session_path)

            cl.login(USERNAME, PASSWORD)

            cl.get_timeline_feed()

            print(
                "[+] Instagram session loaded & verified!"
            )

            return cl

        except Exception as e:

            print(
                f"[!] Cached session invalid ({e}). "
                f"Resetting session..."
            )

            session_path.unlink(missing_ok=True)

    # --------------------------------------------------------
    # FRESH LOGIN
    # --------------------------------------------------------

    print(
        f"[+] Logging in to Instagram as "
        f"'{USERNAME}'..."
    )

    cl = create_fresh_client()

    try:

        cl.login(USERNAME, PASSWORD)

        cl.dump_settings(session_path)

        print(
            f"[+] Login successful! "
            f"Session saved to {SESSION_FILE.name}"
        )

        return cl

    except ChallengeRequired:

        print(
            "[!] Instagram triggered a Challenge. "
            "Resolving..."
        )

        try:

            cl.challenge_resolve(cl.last_json)

            cl.login(USERNAME, PASSWORD)

            cl.dump_settings(session_path)

            print(
                "[+] Challenge resolved & logged in!"
            )

            return cl

        except Exception as challenge_err:

            print(
                f"[X] Failed to resolve challenge: "
                f"{challenge_err}"
            )

            session_path.unlink(missing_ok=True)

            raise challenge_err

    except Exception as e:

        print(
            f"[X] Failed to log in to Instagram: {e}"
        )

        session_path.unlink(missing_ok=True)

        raise e


# ============================================================
# STARTUP
# ============================================================

print("=" * 60)
print("AI CAMERA & INSTAGRAM AUTOMATION - STARTUP")
print("=" * 60)


# ============================================================
# INSTAGRAM LOGIN BEFORE CAMERA
# ============================================================

print(
    "[+] Connecting to Instagram BEFORE opening camera..."
)

instagram_client = None

try:

    instagram_client = get_instagram_client()

    print(
        "[+] Instagram is ready."
    )

except Exception as login_err:

    print(
        f"[X] Instagram startup login failed: "
        f"{login_err}"
    )

    raise


# ============================================================
# LOAD YOLO MODEL
# ============================================================

print(
    "[+] Loading YOLO hand gesture model..."
)

try:

    model = YOLO(
        str(MODEL_FILE)
    )

    print(
        f"[+] YOLO model loaded successfully: "
        f"{MODEL_FILE.name}"
    )

except Exception as e:

    print(
        f"[X] Failed to load YOLO model: {e}"
    )

    raise


# ============================================================
# POSTED HISTORY
# ============================================================

def load_posted_history():

    if HISTORY_FILE.exists():

        try:

            with open(
                HISTORY_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                return set(
                    json.load(f)
                )

        except Exception:

            return set()

    return set()


def save_posted_history(posted_files):

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            list(posted_files),
            f,
            indent=4
        )


# ============================================================
# STATUS OVERLAY
# ============================================================

overlay_status = ""
overlay_until = 0


def set_overlay_status(
    msg,
    duration=3.0
):

    global overlay_status
    global overlay_until

    overlay_status = msg

    overlay_until = (
        time.time() + duration
    )


# ============================================================
# LOCAL IMAGE FRAME - PILLOW
# ============================================================

def create_local_framed_image(
    image_path,
    capture_time
):

    """
    Creates the Instagram image frame locally.

    Frame contains:
        AI SOFT Faisalabad
        Date
        Time

    No VICTORY text is added to the frame.
    """

    from PIL import Image
    from PIL import ImageDraw
    from PIL import ImageFont

    image_path = Path(image_path)

    print(
        "[+] Creating photo frame locally (Pillow)..."
    )

    original = Image.open(
        image_path
    ).convert("RGB")

    original_w, original_h = original.size

    border = FRAME_BORDER
    top_space = FRAME_TOP_SPACE
    bottom_space = FRAME_BOTTOM_SPACE

    final_w = (
        original_w +
        border * 2
    )

    final_h = (
        original_h +
        top_space +
        bottom_space +
        border * 2
    )

    framed = Image.new(
        "RGB",
        (final_w, final_h),
        "white"
    )

    framed.paste(
        original,
        (
            border,
            border + top_space
        )
    )

    draw = ImageDraw.Draw(
        framed
    )

    def load_font(
        paths,
        size
    ):

        for path in paths:

            if Path(path).exists():

                try:

                    return ImageFont.truetype(
                        path,
                        size
                    )

                except Exception:

                    pass

        return ImageFont.load_default()

    bold = load_font(
        [
            "/System/Library/Fonts/"
            "Supplemental/Arial Bold.ttf",

            "/System/Library/Fonts/"
            "Supplemental/Helvetica.ttc",
        ],
        max(
            28,
            original_w // 28
        )
    )

    regular = load_font(
        [
            "/System/Library/Fonts/"
            "Supplemental/Arial.ttf",

            "/System/Library/Fonts/"
            "Supplemental/Helvetica.ttc",
        ],
        max(
            20,
            original_w // 45
        )
    )

    date_text = capture_time.strftime(
        "%d-%B-%Y"
    )

    time_text = capture_time.strftime(
        "%I:%M:%S %p"
    )

    brand_box = draw.textbbox(
        (0, 0),
        FRAME_BRAND_NAME,
        font=bold
    )

    brand_w = (
        brand_box[2] -
        brand_box[0]
    )

    brand_h = (
        brand_box[3] -
        brand_box[1]
    )

    draw.text(
        (
            (final_w - brand_w) // 2,
            border +
            (top_space - brand_h) // 2 -
            5
        ),
        FRAME_BRAND_NAME,
        fill="black",
        font=bold
    )

    info = (
        f"Date: {date_text}"
        f"   |   "
        f"Time: {time_text}"
    )

    info_box = draw.textbbox(
        (0, 0),
        info,
        font=regular
    )

    info_w = (
        info_box[2] -
        info_box[0]
    )

    info_h = (
        info_box[3] -
        info_box[1]
    )

    draw.text(
        (
            (final_w - info_w) // 2,

            border +
            top_space +
            original_h +
            (bottom_space - info_h) // 2 -
            5
        ),
        info,
        fill="black",
        font=regular
    )

    draw.rectangle(
        (
            border // 2,
            border // 2,

            final_w -
            border // 2 -
            1,

            final_h -
            border // 2 -
            1
        ),
        outline="black",
        width=max(
            2,
            border // 8
        )
    )

    framed.save(
        image_path,
        format="JPEG",
        quality=95,
        optimize=True
    )

    print(
        f"[SUCCESS] Local frame created: "
        f"{image_path.name}"
    )

    print(
        f"          Brand: {FRAME_BRAND_NAME}"
    )

    print(
        f"          Date: {date_text}"
    )

    print(
        f"          Time: {time_text}"
    )

    return image_path


# ============================================================
# INSTAGRAM PHOTO UPLOAD WORKER
# ============================================================

def upload_and_delete_worker(
    image_path,
    caption,
    capture_time
):

    """
    Background worker:

    1. Create local frame
    2. Upload photo to Instagram
    3. Save posted history
    4. Delete local photo
    """

    global instagram_client

    image_path = Path(
        image_path
    )

    print()
    print("=" * 60)

    print(
        f"[+] [BACKGROUND THREAD] "
        f"Uploading {image_path.name} "
        f"to Instagram..."
    )

    print("=" * 60)

    set_overlay_status(
        "UPLOADING TO INSTAGRAM...",
        duration=10.0
    )

    success = False

    try:

        if instagram_client is None:

            instagram_client = (
                get_instagram_client()
            )

        image_path = (
            create_local_framed_image(
                image_path=image_path,
                capture_time=capture_time
            )
        )

        media = (
            instagram_client.photo_upload(
                path=str(image_path),
                caption=caption
            )
        )

        print(
            f"[SUCCESS] Uploaded to Instagram! "
            f"Media ID: {media.pk}"
        )

        posted = load_posted_history()

        posted.add(
            image_path.name
        )

        save_posted_history(
            posted
        )

        success = True

    except Exception as e:

        err_msg = str(e)

        if (
            "login_required"
            in err_msg.lower()
            or
            "403"
            in err_msg
        ):

            print(
                "[!] Session expired. "
                "Re-authenticating..."
            )

            try:

                instagram_client = (
                    get_instagram_client(
                        force_new=True
                    )
                )

                media = (
                    instagram_client.photo_upload(
                        path=str(image_path),
                        caption=caption
                    )
                )

                print(
                    f"[SUCCESS] Uploaded after "
                    f"re-login! Media ID: {media.pk}"
                )

                posted = (
                    load_posted_history()
                )

                posted.add(
                    image_path.name
                )

                save_posted_history(
                    posted
                )

                success = True

            except Exception as retry_err:

                print(
                    f"[X] Retry upload failed: "
                    f"{retry_err}"
                )

        else:

            print(
                f"[X] Upload failed: {e}"
            )

    if success:

        if image_path.exists():

            try:

                image_path.unlink()

                print(
                    f"[+] AUTO-DELETED local file "
                    f"from folder: "
                    f"{image_path.name}"
                )

            except Exception as del_err:

                print(
                    f"[!] Failed to delete "
                    f"local file: {del_err}"
                )

        set_overlay_status(
            "POSTED TO INSTAGRAM & AUTO-DELETED!",
            duration=4.0
        )

    else:

        set_overlay_status(
            "INSTAGRAM UPLOAD FAILED!",
            duration=4.0
        )


# ============================================================
# PALM VIDEO THUMBNAIL - OPENCV ONLY
# ============================================================

def create_video_thumbnail(video_path):
    """
    Extract the first usable frame from the palm video using OpenCV.
    No MoviePy dependency is required.
    Returns the JPEG thumbnail path, or None on failure.
    """
    video_path = Path(video_path)
    thumbnail_path = video_path.with_name(
        f"{video_path.stem}_thumbnail.jpg"
    )

    print(
        f"[+] Creating video thumbnail with OpenCV: "
        f"{thumbnail_path.name}"
    )

    cap_thumb = cv2.VideoCapture(str(video_path))

    if not cap_thumb.isOpened():
        print("[X] Could not open palm video for thumbnail creation.")
        return None

    frame = None

    # Try the beginning of the video first, then a few nearby frames
    # in case the very first frame cannot be decoded.
    for _ in range(10):
        ret, candidate = cap_thumb.read()
        if ret and candidate is not None and candidate.size > 0:
            frame = candidate
            break

    cap_thumb.release()

    if frame is None:
        print("[X] Could not read a frame from palm video.")
        return None

    # Instagram/instagrapi expects a JPEG thumbnail.
    if not cv2.imwrite(
        str(thumbnail_path),
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 95]
    ):
        print("[X] Could not save video thumbnail.")
        return None

    if not thumbnail_path.exists() or thumbnail_path.stat().st_size == 0:
        print("[X] Thumbnail file was not created correctly.")
        return None

    print(
        f"[SUCCESS] Video thumbnail created: "
        f"{thumbnail_path.name}"
    )

    return thumbnail_path


# ============================================================
# INSTAGRAM VIDEO UPLOAD WORKER
# ============================================================

def upload_video_and_delete_worker(
    video_path,
    caption
):

    """
    Background worker for PALM video:

    1. Create thumbnail locally with OpenCV
    2. Upload 5-second video to Instagram with explicit thumbnail
    3. Save posted history
    4. Delete local video + thumbnail after successful upload
    """

    global instagram_client

    video_path = Path(video_path)
    thumbnail_path = None

    print()
    print("=" * 60)

    print(
        f"[+] [BACKGROUND THREAD] "
        f"Uploading palm video {video_path.name} "
        f"to Instagram..."
    )

    print("=" * 60)

    set_overlay_status(
        "CREATING PALM VIDEO THUMBNAIL...",
        duration=15.0
    )

    success = False

    try:

        if instagram_client is None:
            instagram_client = get_instagram_client()

        # --------------------------------------------------------
        # CREATE THUMBNAIL WITH OPENCV
        # --------------------------------------------------------

        thumbnail_path = create_video_thumbnail(video_path)

        if thumbnail_path is None:
            raise RuntimeError(
                "Could not create video thumbnail with OpenCV."
            )

        set_overlay_status(
            "UPLOADING PALM VIDEO TO INSTAGRAM...",
            duration=15.0
        )

        print(
            f"[+] Using thumbnail: {thumbnail_path.name}"
        )

        # --------------------------------------------------------
        # INSTAGRAM VIDEO UPLOAD
        # --------------------------------------------------------

        media = instagram_client.video_upload(
            path=str(video_path),
            caption=caption,
            thumbnail=str(thumbnail_path)
        )

        print(
            f"[SUCCESS] Palm video uploaded to Instagram! "
            f"Media ID: {media.pk}"
        )

        posted = load_posted_history()

        posted.add(
            video_path.name
        )

        save_posted_history(
            posted
        )

        success = True

    except Exception as e:

        err_msg = str(e)

        if (
            "login_required" in err_msg.lower()
            or
            "403" in err_msg
        ):

            print(
                "[!] Session expired while uploading video. "
                "Re-authenticating..."
            )

            try:

                instagram_client = get_instagram_client(
                    force_new=True
                )

                # If the thumbnail was not created before the
                # exception, create it now for the retry.
                if thumbnail_path is None:
                    thumbnail_path = create_video_thumbnail(
                        video_path
                    )

                if thumbnail_path is None:
                    raise RuntimeError(
                        "Could not create video thumbnail for retry."
                    )

                media = instagram_client.video_upload(
                    path=str(video_path),
                    caption=caption,
                    thumbnail=str(thumbnail_path)
                )

                print(
                    f"[SUCCESS] Palm video uploaded after "
                    f"re-login! Media ID: {media.pk}"
                )

                posted = load_posted_history()

                posted.add(
                    video_path.name
                )

                save_posted_history(
                    posted
                )

                success = True

            except Exception as retry_err:

                print(
                    f"[X] Video retry upload failed: "
                    f"{retry_err}"
                )

        else:

            print(
                f"[X] Palm video upload failed: {e}"
            )

    # ------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------

    if success:

        if video_path.exists():

            try:

                video_path.unlink()

                print(
                    f"[+] AUTO-DELETED local video: "
                    f"{video_path.name}"
                )

            except Exception as del_err:

                print(
                    f"[!] Failed to delete local video: "
                    f"{del_err}"
                )

        if (
            thumbnail_path is not None
            and
            thumbnail_path.exists()
        ):

            try:

                thumbnail_path.unlink()

                print(
                    f"[+] AUTO-DELETED video thumbnail: "
                    f"{thumbnail_path.name}"
                )

            except Exception as thumb_del_err:

                print(
                    f"[!] Failed to delete video thumbnail: "
                    f"{thumb_del_err}"
                )

        set_overlay_status(
            "PALM VIDEO POSTED & AUTO-DELETED!",
            duration=5.0
        )

    else:

        # Keep the video for troubleshooting if upload failed,
        # but remove the temporary thumbnail.
        if (
            thumbnail_path is not None
            and
            thumbnail_path.exists()
        ):

            try:

                thumbnail_path.unlink()

                print(
                    f"[+] Removed temporary thumbnail after "
                    f"failed upload: {thumbnail_path.name}"
                )

            except Exception as thumb_del_err:

                print(
                    f"[!] Failed to remove thumbnail: "
                    f"{thumb_del_err}"
                )

        set_overlay_status(
            "PALM VIDEO UPLOAD FAILED!",
            duration=5.0
        )


# ============================================================
# RECORD 5-SECOND PALM VIDEO
# ============================================================

def record_palm_video(cap, first_frame, capture_time):

    """
    Records exactly PALM_VIDEO_DURATION seconds from the webcam.

    The video is saved locally first and then uploaded by a
    background worker.
    """

    filename = (
        f"palm_video_"
        f"{capture_time.strftime('%Y%m%d_%H%M%S')}"
        f".mp4"
    )

    video_path = SAVE_DIR / filename

    height, width = first_frame.shape[:2]

    # MP4 writer. If this codec is unavailable, try avc1.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    writer = cv2.VideoWriter(
        str(video_path),
        fourcc,
        PALM_VIDEO_FPS,
        (width, height)
    )

    if not writer.isOpened():

        print(
            "[X] Could not create MP4 video writer."
        )

        return None

    print()
    print("=" * 60)
    print("PALM DETECTED - STARTING 5 SECOND VIDEO!")
    print(
        f"Video will be saved temporarily as: "
        f"{video_path.name}"
    )
    print("=" * 60)

    set_overlay_status(
        "PALM DETECTED - RECORDING 5 SEC VIDEO...",
        duration=PALM_VIDEO_DURATION + 2
    )

    start_time = time.time()
    frame_interval = 1.0 / PALM_VIDEO_FPS
    next_frame_time = start_time

    # First detected frame is included in the video.
    writer.write(first_frame)

    while (
        time.time() - start_time
        < PALM_VIDEO_DURATION
    ):

        ret, frame = cap.read()

        if not ret:
            print(
                "[!] Could not read camera frame during video recording."
            )
            break

        frame = cv2.flip(frame, 1)

        writer.write(frame)

        # Keep the live camera window responsive during recording.
        display_frame = frame.copy()

        elapsed = time.time() - start_time
        remaining = max(
            0,
            PALM_VIDEO_DURATION - elapsed
        )

        cv2.putText(
            display_frame,
            f"RECORDING PALM VIDEO: {remaining:.1f}s",
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            3
        )

        cv2.imshow(
            "AI Camera & Instagram Poster",
            display_frame
        )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

        # Pace recording close to the requested FPS.
        next_frame_time += frame_interval
        sleep_time = next_frame_time - time.time()

        if sleep_time > 0:
            time.sleep(sleep_time)

    writer.release()

    if not video_path.exists() or video_path.stat().st_size == 0:

        print(
            "[X] Video file was not created correctly."
        )

        return None

    print(
        f"[SUCCESS] 5-second palm video recorded: "
        f"{video_path.name}"
    )

    return video_path


# ============================================================
# YOLO VICTORY + PALM DETECTION
# ============================================================

def detect_gestures(frame):

    """
    Runs YOLO on current frame.

    peace = VICTORY
    palm  = PALM

    VICTORY is used for the photo function.
    PALM is used for the 5-second video function.
    """

    results = model(
        frame,
        conf=YOLO_CONFIDENCE,
        imgsz=YOLO_IMAGE_SIZE,
        verbose=False
    )

    result = results[0]

    annotated_frame = frame.copy()

    victory_detected = False
    palm_detected = False

    if result.boxes is not None:

        for box in result.boxes:

            class_id = int(
                box.cls[0]
            )

            confidence = float(
                box.conf[0]
            )

            class_name = (
                model.names[class_id]
            )

            class_name_lower = class_name.lower()

            # ------------------------------------------------
            # PEACE = VICTORY
            # ------------------------------------------------

            if class_name_lower == "peace":

                victory_detected = True

                display_name = "VICTORY"

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )

                cv2.rectangle(
                    annotated_frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    3
                )

                label = (
                    f"{display_name} - "
                    f"{confidence:.0%}"
                )

                cv2.putText(
                    annotated_frame,
                    label,
                    (
                        x1,
                        max(
                            y1 - 10,
                            30
                        )
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2
                )

            # ------------------------------------------------
            # PALM = 5 SECOND VIDEO
            # ------------------------------------------------

            elif class_name_lower == "palm":

                palm_detected = True

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )

                cv2.rectangle(
                    annotated_frame,
                    (x1, y1),
                    (x2, y2),
                    (255, 0, 0),
                    3
                )

                label = (
                    f"PALM - "
                    f"{confidence:.0%}"
                )

                cv2.putText(
                    annotated_frame,
                    label,
                    (
                        x1,
                        max(
                            y1 - 10,
                            30
                        )
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (255, 0, 0),
                    2
                )

    return (
        victory_detected,
        palm_detected,
        annotated_frame
    )


# ============================================================
# MAIN APPLICATION LOOP
# ============================================================

def run_app():

    # --------------------------------------------------------
    # OPEN CAMERA
    # --------------------------------------------------------

    cap = cv2.VideoCapture(
        CAMERA_INDEX
    )

    if not cap.isOpened():

        print(
            "ERROR: Camera could not be opened."
        )

        print(
            "Try changing CAMERA_INDEX "
            "from 0 to 1."
        )

        return

    # --------------------------------------------------------
    # CAMERA RESOLUTION
    # --------------------------------------------------------

    cap.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        1280
    )

    cap.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        720
    )

    # --------------------------------------------------------
    # START MESSAGE
    # --------------------------------------------------------

    print("=" * 60)

    print(
        "AI CAMERA & INSTAGRAM AUTOMATION"
    )

    print("=" * 60)

    print(
        "Camera started."
    )

    print(
        "Show a Victory / Peace sign ✌ "
        "for a PHOTO."
    )

    print(
        "Show an open Palm for a 5-second VIDEO."
    )

    print(
        "Photos and videos will be uploaded to Instagram "
        "and auto-deleted after successful upload."
    )

    print(
        "Press Q to quit."
    )

    print("=" * 60)

    # --------------------------------------------------------
    # COUNTERS
    # --------------------------------------------------------

    victory_counter = 0

    last_capture_time = 0

    last_palm_video_time = 0

    # Prevent repeated palm triggers while recording/uploading.
    palm_video_busy = False

    capture_flash_until = 0

    # ========================================================
    # CAMERA LOOP
    # ========================================================

    while True:

        success, frame = cap.read()

        if not success:

            print(
                "ERROR: Could not read frame."
            )

            break

        # ----------------------------------------------------
        # MIRROR CAMERA
        # ----------------------------------------------------

        frame = cv2.flip(
            frame,
            1
        )

        # ----------------------------------------------------
        # CLEAN FRAME
        # YOLO boxes/labels will NOT be saved in photo.
        # ----------------------------------------------------

        clean_frame = frame.copy()

        # ----------------------------------------------------
        # YOLO DETECTION
        # ----------------------------------------------------

        (
            victory_detected,
            palm_detected,
            annotated_frame
        ) = detect_gestures(frame)

        # ----------------------------------------------------
        # CONSECUTIVE VICTORY FRAME COUNT
        # ----------------------------------------------------

        if victory_detected:

            victory_counter += 1

        else:

            victory_counter = 0

        # ----------------------------------------------------
        # DISPLAY VICTORY STATUS
        # ----------------------------------------------------

        if victory_detected:

            status_text = (
                f"VICTORY SIGN DETECTED! "
                f"{victory_counter}/"
                f"{REQUIRED_FRAMES}"
            )

            cv2.putText(
                annotated_frame,
                status_text,
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 0),
                3
            )

        else:

            cv2.putText(
                annotated_frame,
                "Show Victory Sign or Palm",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2
            )

        # ----------------------------------------------------
        # PALM STATUS
        # ----------------------------------------------------

        if palm_detected:

            cv2.putText(
                annotated_frame,
                "PALM DETECTED - 5 SEC VIDEO",
                (20, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 0, 0),
                2
            )

        # ----------------------------------------------------
        # UPLOAD STATUS OVERLAY
        # ----------------------------------------------------

        if time.time() < overlay_until:

            cv2.putText(
                annotated_frame,
                overlay_status,
                (20, 140),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 0),
                2
            )

        # ----------------------------------------------------
        # CURRENT TIME
        # ----------------------------------------------------

        current_time = time.time()

        # ====================================================
        # VICTORY -> PHOTO
        # ====================================================

        if (
            victory_counter >= REQUIRED_FRAMES
            and
            (
                current_time -
                last_capture_time
                >
                CAPTURE_COOLDOWN
            )
        ):

            now = datetime.now()

            filename = (
                f"capture_"
                f"{now.strftime('%Y%m%d_%H%M%S')}"
                f".jpg"
            )

            image_path = (
                SAVE_DIR /
                filename
            )

            # ------------------------------------------------
            # SAVE CLEAN PHOTO
            # ------------------------------------------------

            cv2.imwrite(
                str(image_path),
                clean_frame
            )

            # ------------------------------------------------
            # INSTAGRAM CAPTION
            # ------------------------------------------------

            caption = (
                "This picture taken from AI automation "
                "script made by AI SOFT Faisalabad.\n"
                f"Date: {now.strftime('%d-%B-%Y')}\n"
                f"Time: {now.strftime('%I:%M:%S %p')}"
            )

            print()

            print("=" * 60)

            print(
                "VICTORY SIGN DETECTED - PHOTO CAPTURED!"
            )

            print(
                f"Picture saved temporarily: "
                f"{image_path.name}"
            )

            print(
                f"Caption: {caption}"
            )

            print("=" * 60)

            # ------------------------------------------------
            # BACKGROUND INSTAGRAM PHOTO UPLOAD
            # ------------------------------------------------

            t = threading.Thread(
                target=upload_and_delete_worker,
                args=(
                    image_path,
                    caption,
                    now
                ),
                daemon=True
            )

            t.start()

            capture_flash_until = (
                time.time() + 0.4
            )

            last_capture_time = (
                time.time()
            )

            victory_counter = 0

        # ====================================================
        # PALM -> 5 SECOND VIDEO
        # ====================================================

        elif (
            palm_detected
            and
            not palm_video_busy
            and
            (
                current_time -
                last_palm_video_time
                >
                PALM_VIDEO_COOLDOWN
            )
        ):

            now = datetime.now()

            # Lock palm trigger before recording so the same held
            # palm cannot start multiple recordings.
            palm_video_busy = True

            # Record the 5-second video.
            video_path = record_palm_video(
                cap,
                clean_frame,
                now
            )

            if video_path is not None:

                video_caption = (
                    "This 5-second palm video was captured "
                    "from AI automation script made by "
                    "AI SOFT Faisalabad.\n"
                    f"Date: {now.strftime('%d-%B-%Y')}\n"
                    f"Time: {now.strftime('%I:%M:%S %p')}"
                )

                print()

                print("=" * 60)

                print(
                    "PALM DETECTED - 5 SECOND VIDEO READY!"
                )

                print(
                    f"Video saved temporarily: "
                    f"{video_path.name}"
                )

                print(
                    f"Caption: {video_caption}"
                )

                print("=" * 60)

                # ------------------------------------------------
                # BACKGROUND INSTAGRAM VIDEO UPLOAD
                # ------------------------------------------------

                video_thread = threading.Thread(
                    target=upload_video_and_delete_worker,
                    args=(
                        video_path,
                        video_caption
                    ),
                    daemon=True
                )

                video_thread.start()

                # Release the trigger lock only after the background
                # upload worker finishes. This prevents duplicate
                # videos while the palm remains in front of camera.
                def release_palm_video_lock(worker_thread):
                    nonlocal palm_video_busy
                    worker_thread.join()
                    palm_video_busy = False
                    print(
                        "[+] Palm video trigger unlocked."
                    )

                threading.Thread(
                    target=release_palm_video_lock,
                    args=(video_thread,),
                    daemon=True
                ).start()

            else:
                # Recording failed, so allow another palm attempt.
                palm_video_busy = False

            last_palm_video_time = time.time()

            victory_counter = 0

        # ====================================================
        # PHOTO FLASH
        # ====================================================

        if (
            time.time() <
            capture_flash_until
        ):

            cv2.rectangle(
                annotated_frame,
                (0, 0),
                (
                    annotated_frame.shape[1],
                    annotated_frame.shape[0]
                ),
                (255, 255, 255),
                -1
            )

            cv2.putText(
                annotated_frame,
                "PHOTO CAPTURED!",
                (250, 350),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                (0, 0, 0),
                4
            )

        # ====================================================
        # SHOW LIVE VIDEO
        # ====================================================

        cv2.imshow(
            "AI Camera & Instagram Poster",
            annotated_frame
        )

        # ----------------------------------------------------
        # QUIT
        # ----------------------------------------------------

        if (
            cv2.waitKey(1) & 0xFF
            ==
            ord("q")
        ):

            break

    # ========================================================
    # CLEANUP
    # ========================================================

    cap.release()

    cv2.destroyAllWindows()

    print(
        "Camera closed."
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    run_app()
