import zlib


def decompress_field(data):
    if not data:
        return data  # Returns None or empty string as-is
    
    # If SQLite already returned a string (e.g., uncompressed data), return it
    if isinstance(data, str):
        return data
        
    # Keep decompressing in a loop as long as the data is compressed bytes
    while isinstance(data, bytes):
        try:
            # Attempt to decompress
            data = zlib.decompress(data)
        except zlib.error:
            # A zlib.error means we've reached a layer that is NOT compressed.
            # This is our final raw payload, so we break out of the loop.
            break
            
    # Now that all compression layers are stripped, decode back to a string
    if isinstance(data, bytes):
        return data.decode('utf-8')
        
    return data



def compress_field(data):
    if not data:
        return data  # Returns None or empty string as-is
    
    if isinstance(data, str):
        data = data.encode('utf-8')  # Convert string to bytes
    
    return zlib.compress(data)