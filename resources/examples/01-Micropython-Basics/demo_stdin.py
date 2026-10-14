"""
Test script for stdin, stdout, and stderr on MicroPython
Compatible with standard MicroPython (no f-strings, proper sleep methods)

Interactive reads use a timeout so the script also completes in automated runs.
"""

import sys
import time
import select

INPUT_TIMEOUT_MS = 2000


def read_with_timeout(stream, size=None):
    """Read only when input arrives before the bounded prompt timeout."""
    poller = select.poll()
    poller.register(stream, select.POLLIN)
    if not poller.poll(INPUT_TIMEOUT_MS):
        return None
    return stream.readline() if size is None else stream.read(size)

def test_stdout():
    """Test standard output functionality"""
    print("\n=== Testing stdout ===")
    
    # Test 1: Simple string output
    sys.stdout.write("Test 1: Standard text output\n")
    
    # Test 2: Multiple writes
    sys.stdout.write("Test 2: ")
    sys.stdout.write("concatenated ")
    sys.stdout.write("output\n")
    
    # Test 3: Binary output
    binary_data = b"Test 3: Binary output: \x48\x65\x6c\x6c\x6f\n"
    sys.stdout.buffer.write(binary_data)
    
    # Test 5: Print with various data types (avoid f-strings)
    print("Test 5: Integer:", 123, "Float:", 45.67, "Hex:", 0xFF)
    
    print("stdout tests completed\n")

def test_stderr():
    """Test standard error output"""
    print("\n=== Testing stderr ===")
    
    # Test 1: Error message
    sys.stderr.write("Test 1: This is an error message\n")
    
    # Test 2: Exception simulation
    try:
        raise ValueError("Test error")
    except ValueError as e:
        sys.stderr.write("Test 2: Caught exception: " + str(e) + "\n")
    
    # Test 3: Binary error output
    sys.stderr.buffer.write(b"Test 3: Binary error output\n")
    
    # Test 4: Multiple error lines
    for i in range(3):
        sys.stderr.write("Test 4: Error line " + str(i+1) + "\n")
    
    print("stderr tests completed\n")

def test_stdin():
    """Test standard input functionality"""
    print("\n=== Testing stdin ===")
    
    # Test 1: Read a line when one is available.
    sys.stdout.write("Test 1: Enter a line of text: ")

    line = read_with_timeout(sys.stdin)
    if line:
        text = line.rstrip('\r\n')
        print("You entered:", text)
    else:
        print("no input received")
    
    # Test 2: Binary read
    sys.stdout.write("\nTest 2: Enter 5 characters: ")
    binary_input = read_with_timeout(sys.stdin.buffer, 5)
    if binary_input:
        print("Binary read:", binary_input)
        # Convert to hex string manually
        hex_str = ""
        for b in binary_input:
            hex_str += "{:02x} ".format(b)
        print("As hex:", hex_str)
    else:
        print("no binary input received")

def interactive_echo_test():
    """Interactive echo test - runs until Ctrl+C"""
    print("\n=== Interactive Echo Test ===")
    print("Type anything and it will be echoed back")
    print("Press Ctrl+C to exit this test\n")
    
    try:
        while True:
            # Read one character at a time
            char = sys.stdin.read(1)
            if char:
                # Echo back what we received
                sys.stdout.write(char)

            # Small delay to prevent CPU spinning
            time.sleep_ms(10)

    except KeyboardInterrupt:
        print("\n\nEcho test stopped")

def performance_test():
    """Test throughput of stdin/stdout"""
    print("\n=== Performance Test ===")
    
    # Test stdout throughput
    test_data = b"X" * 1000
    start = time.ticks_us()
    
    if start is None:
        print("Performance test skipped: time.ticks_us not available")
        return
    
    for _ in range(100):
        sys.stdout.buffer.write(test_data)
    
    elapsed = time.ticks_diff(time.ticks_us(), start)
    
    bytes_written = 100 * len(test_data)
    speed = (bytes_written * 1000000) / elapsed

    print("Wrote {} bytes in {:.2f} ms".format(bytes_written, elapsed/1000))
    print("Speed: {:.2f} KB/s".format(speed/1024))

def check_stdin_availability():
    """Check stdin availability and features"""
    print("\n=== System Information ===")
    
    # Check available attributes
    stdin_attrs = [attr for attr in dir(sys.stdin) if not attr.startswith('_')]
    stdout_attrs = [attr for attr in dir(sys.stdout) if not attr.startswith('_')]
    stderr_attrs = [attr for attr in dir(sys.stderr) if not attr.startswith('_')]
    
    print("sys.stdin available:", stdin_attrs)
    print("sys.stdout available:", stdout_attrs)
    print("sys.stderr available:", stderr_attrs)
    
    # Check buffer support
    print("\nsys.stdin.buffer available:", hasattr(sys.stdin, 'buffer'))
    print("sys.stdout.buffer available:", hasattr(sys.stdout, 'buffer'))
    print("sys.stderr.buffer available:", hasattr(sys.stderr, 'buffer'))
    
    # Check if stdin is a TTY (REPL)
    try:
        is_tty = hasattr(sys.stdin, 'isatty') and sys.stdin.isatty()
        print("Is stdin a TTY (REPL)?:", is_tty)
    except:
        print("Cannot determine if stdin is TTY")

def run_all_tests():
    """Run all tests in sequence"""
    print("=" * 50)
    print("MicroPython STDIO/STDOUT/STDERR Test Suite")
    print("=" * 50)
    
    # System info
    check_stdin_availability()
    
    # Basic tests
    test_stdout()
    test_stderr()
    
    test_stdin()
    
    # Performance test
    performance_test()
    
    # Interactive echo test (optional)
    sys.stdout.write("\nRun interactive echo test? (y/n): ")
    response = read_with_timeout(sys.stdin)
    response = response.strip().lower() if response else ""
    
    if response == b'y' or response == 'y':
        interactive_echo_test()
    
    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)

# Run the tests
if __name__ == "__main__":
    run_all_tests()
