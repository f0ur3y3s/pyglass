import struct
import cv2
import numpy as np


def read_bmp_data(filename):
    """Reads BMP image data, skipping the header."""
    with open(filename, "rb") as f:
        f.seek(62)  # Skip BMP header (assuming a 62-byte header for 1-bit BMP)
        return f.read()


def split_into_packets(data, packet_size=194):
    """Splits BMP data into fixed-size packets."""
    return [data[i : i + packet_size] for i in range(0, len(data), packet_size)]


def create_packets(bmp_data):
    """Formats BMP data into packets with necessary headers."""
    packets = split_into_packets(bmp_data)
    formatted_packets = []

    for index, packet in enumerate(packets):
        if index == 0:
            header = [
                0x15,
                index & 0xFF,
                0x00,
                0x1C,
                0x00,
                0x00,
            ]  # First packet with address
        else:
            header = [0x15, index & 0xFF]  # Other packets

        formatted_packets.append(bytes(header) + packet)

    return formatted_packets


def send_packets(ble_interface, packets):
    """Sends all packets via BLE interface."""
    for packet in packets:
        ble_interface.send(packet)  # Replace with actual BLE send method

    # Send end packet command
    ble_interface.send(bytes([0x20, 0x0D, 0x0E]))

    # Wait for confirmation (implementation depends on BLE response handling)
    response = ble_interface.receive()
    if response == b"ACK":  # Example ACK handling
        send_crc_check(ble_interface, packets)


def send_crc_check(ble_interface, packets):
    """Calculates and sends CRC checksum."""
    crc_data = b"".join(packets)  # Concatenate all packet data
    crc = calculate_crc(crc_data)
    ble_interface.send(bytes([0x16]) + struct.pack("<H", crc))


def calculate_crc(data):
    """Simple XOR-based checksum calculation."""
    crc = 0
    for byte in data:
        crc ^= byte  # Simple XOR checksum; replace with proper CRC algorithm if needed
    return crc


def extract_video_frame(video_path):
    """Extracts frames from video, maintains aspect ratio, crops, and converts them to 1-bit BMP format."""
    cap = cv2.VideoCapture(video_path)
    target_width, target_height = 576, 136  # Required BMP dimensions

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Get original dimensions
        h, w, _ = frame.shape
        aspect_ratio = w / h

        # Determine new size while maintaining aspect ratio
        if w / target_width > h / target_height:
            new_w = target_width
            new_h = int(target_width / aspect_ratio)
        else:
            new_h = target_height
            new_w = int(target_height * aspect_ratio)

        resized_frame = cv2.resize(frame, (new_w, new_h))

        # Crop to target dimensions
        start_x = (new_w - target_width) // 2
        start_y = (new_h - target_height) // 2
        cropped_frame = resized_frame[
            start_y : start_y + target_height, start_x : start_x + target_width
        ]

        gray = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
        _, bw = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)  # Convert to 1-bit

        yield bw.tobytes()  # Yield binary data of the frame

    cap.release()


# Example usage
if __name__ == "__main__":

    class MockBLEInterface:
        def send(self, data):
            print(f"Sending: {data.hex()}")

        def receive(self):
            return b"ACK"  # Mock ACK response

    ble = MockBLEInterface()
    for frame_data in extract_video_frame("video.mp4"):
        packets = create_packets(frame_data)
        send_packets(ble, packets)
