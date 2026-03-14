import heapq
from collections import Counter
from PIL import Image
import io
import os
import traceback
import pickle

class HuffmanNode:
    def __init__(self, char, freq):
        self.char = char
        self.freq = freq
        self.left = None
        self.right = None

    def __lt__(self, other):
        return self.freq < other.freq


class HuffmanCoder:
    def __init__(self):
        self.codes = {}
        self.reverse_mapping = {}

    def build_tree(self, data):
        frequency = Counter(data)
        priority_queue = [HuffmanNode(char, freq) for char, freq in frequency.items()]
        heapq.heapify(priority_queue)

        while len(priority_queue) > 1:
            node1 = heapq.heappop(priority_queue)
            node2 = heapq.heappop(priority_queue)
            merged = HuffmanNode(None, node1.freq + node2.freq)
            merged.left = node1
            merged.right = node2
            heapq.heappush(priority_queue, merged)
        return heapq.heappop(priority_queue)

    def make_codes_helper(self, root, current_code):
        if root is None: return
        if root.char is not None:
            self.codes[root.char] = current_code
            self.reverse_mapping[current_code] = root.char
            return
        self.make_codes_helper(root.left, current_code + "0")
        self.make_codes_helper(root.right, current_code + "1")

    def encode(self, data):
        root = self.build_tree(data)
        self.make_codes_helper(root, "")
        encoded_text = "".join([self.codes[char] for char in data])
        return encoded_text, self.reverse_mapping

    def decode(self, encoded_data, reverse_mapping):
        current_code = ""
        decoded_data = []
        for bit in encoded_data:
            current_code += bit
            if current_code in reverse_mapping:
                decoded_data.append(reverse_mapping[current_code])
                current_code = ""
        return decoded_data


# --- פונקציות העיבוד והדחיסה ---

def apply_floyd_steinberg_color(image, levels=4):
    """ גרסה צבעונית לדית'רינג עם שליטה ברמת הפירוט """
    img = image.convert('RGB')
    pixels = img.load()
    width, height = img.size

    # חישוב צעד הקוונטיזציה (עבור 4 רמות זה 85, עבור 8 זה 32)
    step = 255 // (levels - 1)

    for y in range(height):
        for x in range(width):
            old_r, old_g, old_b = pixels[x, y]

            new_r = int(round(old_r / step) * step)
            new_g = int(round(old_g / step) * step)
            new_b = int(round(old_b / step) * step)

            pixels[x, y] = (new_r, new_g, new_b)
            err_r, err_g, err_b = old_r - new_r, old_g - new_g, old_b - new_b

            for dx, dy, factor in [(1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)]:
                if 0 <= x + dx < width and 0 <= y + dy < height:
                    r, g, b = pixels[x + dx, y + dy]
                    pixels[x + dx, y + dy] = (
                        max(0, min(255, int(r + err_r * factor))),
                        max(0, min(255, int(g + err_g * factor))),
                        max(0, min(255, int(b + err_b * factor)))
                    )
    return img


def string_to_bytes(bit_string):
    padded_info = 8 - len(bit_string) % 8
    bit_string += "0" * padded_info
    header = format(padded_info, '08b')
    bit_string = header + bit_string
    b = bytearray()
    for i in range(0, len(bit_string), 8):
        b.append(int(bit_string[i:i + 8], 2))
    return bytes(b)


def bytes_to_string(byte_data):
    bit_string = "".join(format(byte, '08b') for byte in byte_data)
    padded_info = int(bit_string[:8], 2)
    bit_string = bit_string[8:]
    return bit_string[:-padded_info] if padded_info > 0 else bit_string


def compress_image(image_path):
    img = Image.open(image_path).convert('RGB')

    # אופטימיזציה: אם התמונה ענקית, נקטין אותה כדי שהדחיסה תהיה יעילה באמת
    w, h = img.size
    if w > 1200 or h > 1200:
        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)

    # 1. איבוד מידע חכם (Dithering)
    dithered_img = apply_floyd_steinberg_color(img, levels=4)

    # 2. שליפת כל נתוני הפיקסלים (RGB Tuples)
    pixel_data = list(dithered_img.getdata())

    # 3. דחיסת הופמן
    coder = HuffmanCoder()
    encoded_bits, mapping = coder.encode(pixel_data)

    return encoded_bits, mapping, dithered_img.size


def decompress_to_image(encoded_bits, mapping, size):
    coder = HuffmanCoder()
    pixel_data = coder.decode(encoded_bits, mapping)

    # יצירת תמונה חדשה והזנת הפיקסלים
    img = Image.new('RGB', size)
    img.putdata([tuple(p) if isinstance(p, list) else p for p in pixel_data])
    return img

def save_compressed_p2p(filename, bits_as_bytes, mapping, size):
    """ אורז את כל נתוני הדחיסה לקובץ אחד """
    data_to_save = {
        'bits': bits_as_bytes,
        'mapping': mapping,
        'size': size
    }
    with open(filename, 'wb') as f:
        pickle.dump(data_to_save, f)
    print(f"File saved: {filename} ({os.path.getsize(filename) / 1024:.2f} KB)")

def load_compressed_p2p(filename):
    """ פורק את נתוני הדחיסה מהקובץ """
    with open(filename, 'rb') as f:
        data = pickle.load(f)
    return data['bits'], data['mapping'], data['size']

# --- בדיקת המנוע ---
# --- בדיקת המנוע המלאה ---
if __name__ == "__main__":
    # 1. הגדרות נתיבים
    test_img = "heavy_test.bmp"  # התמונה הכבדה שיצרנו
    compressed_file = "test_package.p2p"

    if not os.path.exists(test_img):
        print(f"File {test_img} not found! Run the generator first.")
    else:
        try:
            print("--- Stage 1: Compression & Packing ---")
            original_size = os.path.getsize(test_img)

            # דחיסה בזיכרון
            bits, map_data, img_size = compress_image(test_img)
            compressed_bits_bytes = string_to_bytes(bits)

            # שמירה פיזית לקובץ .p2p
            save_compressed_p2p(compressed_file, compressed_bits_bytes, map_data, img_size)

            p2p_size = os.path.getsize(compressed_file)
            print(f"Original: {original_size / (1024 * 1024):.2f} MB")
            print(f"P2P File: {p2p_size / 1024:.2f} KB")
            print(f"Total Efficiency: {(1 - p2p_size / original_size) * 100:.2f}% reduction")

            print("\n--- Stage 2: Loading & Unpacking ---")
            # טעינה מהקובץ הפיזי
            loaded_bits_bytes, loaded_map, loaded_size = load_compressed_p2p(compressed_file)

            # המרה חזרה למחרוזת ביטים
            bits_str = bytes_to_string(loaded_bits_bytes)

            # שחזור לתמונה
            recovered_img = decompress_to_image(bits_str, loaded_map, loaded_size)

            print("Success! Showing the recovered image...")
            recovered_img.show()

        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
