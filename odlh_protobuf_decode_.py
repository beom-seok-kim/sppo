import json
import struct

WIRE_TYPE_VARINT = 0
WIRE_TYPE_64BIT = 1
WIRE_TYPE_LENGTH_DELIMITED = 2
WIRE_TYPE_32BIT = 5

class BufferReader:
    def __init__(self, buffer):
        self.buffer = buffer
        self.offset = 0
        self.saved_offset = 0

    def read_varint(self):
        value, self.offset = self._decode_varint(self.buffer, self.offset)
        return value

    def read_buffer(self, length):
        self._check_byte(length)
        result = self.buffer[self.offset:self.offset + length]
        self.offset += length
        return result

    def try_skip_grpc_header(self):
        backup_offset = self.offset
        if self.buffer[self.offset] == 0 and self.left_bytes() >= 5:
            self.offset += 1
            length = struct.unpack_from('>I', self.buffer, self.offset)[0]
            self.offset += 4
            if length > self.left_bytes():
                self.offset = backup_offset

    def left_bytes(self):
        return len(self.buffer) - self.offset

    def _check_byte(self, length):
        bytes_available = self.left_bytes()
        if length > bytes_available:
            raise ValueError(f"Not enough bytes left. Requested: {length}, left: {bytes_available}")

    def checkpoint(self):
        self.saved_offset = self.offset

    def reset_to_checkpoint(self):
        self.offset = self.saved_offset

    @staticmethod
    def _decode_varint(buffer, pos):
        shift = 0
        result = 0
        start_pos = pos
        while True:
            byte = buffer[pos]
            pos += 1
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                break
            shift += 7
        return result, pos, (start_pos, pos)

def decode_varint_parts(value):
    result = []
    result.append({"type": "uint", "value": value})

    int32_value = struct.unpack('<i', struct.pack('<I', value & 0xFFFFFFFF))[0]
    int64_value = struct.unpack('<q', struct.pack('<Q', value & 0xFFFFFFFFFFFFFFFF))[0]

    if int32_value != value:
        result.append({"type": "int32", "value": int32_value})
    if int64_value != value:
        result.append({"type": "int64", "value": int64_value})

    signed_value = interpret_as_signed_type(value)
    if signed_value != value:
        result.append({"type": "sint", "value": signed_value})

    return result

def decode_fixed32(value):
    float_value = struct.unpack('<f', struct.pack('<I', value))[0]
    return [
        {"type": "float", "value": float_value},
        {"type": "int", "value": value}
    ]

def decode_fixed64(value):
    double_value = struct.unpack('<d', struct.pack('<Q', value))[0]
    return [
        {"type": "double", "value": double_value},
        {"type": "int", "value": value}
    ]

def decode_length_delimited(buffer, pos):
    length, pos, _ = BufferReader._decode_varint(buffer, pos)
    result = buffer[pos:pos + length]
    pos += length
    try:
        result_str = result.decode('utf-8')
        return {"type": "string", "value": result_str, "hex": buffer_to_pretty_hex(result)}, pos
    except UnicodeDecodeError:
        try:
            nested_message = decode_protobuf(result)
            return {"type": "protobuf", "value": nested_message, "hex": buffer_to_pretty_hex(result)}, pos
        except Exception:
            return {"type": "bytes", "value": buffer_to_pretty_hex(result), "hex": buffer_to_pretty_hex(result)}, pos

def decode_field(buffer, pos):
    key, pos, key_range = BufferReader._decode_varint(buffer, pos)
    field_number = key >> 3
    wire_type = key & 0x07
    value_range = (pos, pos)
    original_value = buffer[key_range[0]:pos]
    if wire_type == WIRE_TYPE_VARINT:
        value, pos, value_range = BufferReader._decode_varint(buffer, pos)
        value = decode_varint_parts(value)
    elif wire_type == WIRE_TYPE_64BIT:
        value = struct.unpack_from('<Q', buffer, pos)[0]
        pos += 8
        value = decode_fixed64(value)
        value_range = (value_range[0], pos)
    elif wire_type == WIRE_TYPE_LENGTH_DELIMITED:
        value, pos = decode_length_delimited(buffer, pos)
        value_range = (value_range[0], pos)
    elif wire_type == WIRE_TYPE_32BIT:
        value = struct.unpack_from('<I', buffer, pos)[0]
        pos += 4
        value = decode_fixed32(value)
        value_range = (value_range[0], pos)
    else:
        raise ValueError(f"Unsupported wire type: {wire_type}")
    
    field_info = {
        "Byte Range": f"{key_range[0]}-{value_range[1]}",
        "Field Number": field_number,
        "Type": wire_type_to_string(wire_type),
        "Original Hex": buffer_to_pretty_hex(original_value),
        "Content": value
    }

    return field_info, pos

def decode_protobuf(buffer):
    pos = 0
    decoded_message = []
    while pos < len(buffer):
        field_info, pos = decode_field(buffer, pos)
        decoded_message.append(field_info)
    return decoded_message

def wire_type_to_string(wire_type):
    return {
        WIRE_TYPE_VARINT: "varint",
        WIRE_TYPE_64BIT: "fixed64",
        WIRE_TYPE_LENGTH_DELIMITED: "length_delimited",
        WIRE_TYPE_32BIT: "fixed32"
    }.get(wire_type, "unknown")

def interpret_as_signed_type(n):
    if n & 1 == 0:
        return n >> 1
    else:
        return -((n + 1) >> 1)

def interpret_as_twos_complement(n, bits):
    if (n >> (bits - 1)) & 1:
        return n - (1 << bits)
    else:
        return n

def buffer_to_pretty_hex(buffer):
    return ' '.join(f'{byte:02x}' for byte in buffer)

# Setting the File Path
file_path = r'C:\Users\Your\Path\serialized_data.bin'
output_file_path = r'C:\Users\Your\Path\decoded_data.json'

with open(file_path, 'rb') as file:
    binary_data = file.read()

decoded_message = decode_protobuf(binary_data)

with open(output_file_path, 'w', encoding='utf-8') as json_file:
    json.dump(decoded_message, json_file, ensure_ascii=False, indent=4)

print(f"Decoded data has been saved to {output_file_path}")
