import os
import sys
import struct

# Standard Curses configuration initialization for cross-platform terminals
try:
	import curses
except ImportError:
	print("[-] ERROR: Curses module not found! Please run: pip install windows-curses")
	sys.exit(1)

# Official Commodore 5-to-4 GCR Conversion Lookup Matrix Table
GCR_TO_NYBBLE = {
	0x0A: 0x0, 0x0B: 0x1, 0x12: 0x2, 0x13: 0x3,
	0x0E: 0x4, 0x0F: 0x5, 0x16: 0x6, 0x17: 0x7,
	0x09: 0x8, 0x19: 0x9, 0x1A: 0xA, 0x1B: 0xB,
	0x0D: 0xC, 0x1D: 0xD, 0x1E: 0xE, 0x15: 0xF
}

def decode_gcr_nybbles_to_bytes(nybble_list):
	"""Combines consecutive pairs of 4-bit nybbles into standard 8-bit data bytes."""
	standard_bytes = []
	for i in range(0, len(nybble_list) - 1, 2):
		standard_bytes.append((nybble_list[i] << 4) | nybble_list[i + 1])
	return standard_bytes

def get_user_inputs_and_validate():
	"""Interactive command prompt launcher that collects track targets from the user."""
	print("=" * 65)
	print("    CBM 1541 READ-HEAD HARDWARE GCR BITSTREAM SIMULATOR GUIDE")
	print("=" * 65)
	
	file_path = input("[?] Name of .G64 to read? ").strip().strip('"')
	if not os.path.exists(file_path):
		print(f"[-] ERROR: File cannot be found at: {file_path}")
		sys.exit(1)
		
	try:
		track_target = float(input("[?] Enter Track to inspect (1.0 to 42.5): "))
		if track_target < 1.0 or track_target > 42.5:
			raise ValueError
	except ValueError:
		print("[-] ERROR: Invalid physical track entry bounds!")
		sys.exit(1)
		
	return file_path, track_target
def main_simulation_canvas(stdscr, file_path, target_track):
	# Setup clean interface color theme registries
	curses.start_color()
	curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)   # Active metrics
	curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Header data panels
	curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Sector hex matrix dump
	curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)    # Sync alarm blink banner
	
	curses.noecho()
	curses.cbreak()
	stdscr.keypad(True)
	
	with open(file_path, "rb") as f:
		payload = bytearray(f.read())

	if payload[:8] != b"GCR-1541":
		stdscr.clear()
		print("[-] CRITICAL: Invalid G64 File Signature!")
		sys.exit(1)

	# Dynamically map the user's float track entry straight to the G64 offset table
	g64_idx = int(round((target_track - 1.0) * 2))
	offset_ptr_pos = 12 + (g64_idx * 4)
	
	track_offset = struct.unpack("<I", payload[offset_ptr_pos : offset_ptr_pos + 4])[0]
	if track_offset == 0:
		stdscr.clear()
		stdscr.addstr(2, 2, f"ERROR: Track {target_track} does not exist in this image file.")
		stdscr.getch()
		return

	track_len = struct.unpack("<H", payload[track_offset : track_offset + 2])[0]
	gcr_bytes = payload[track_offset + 2 : track_offset + 2 + track_len]
	bit_stream_array = []
	for b in gcr_bytes:
		for bit_pos in range(7, -1, -1):
			bit_stream_array.append((b >> bit_pos) & 1)
			
	total_track_bits = len(bit_stream_array)

	# --- PURE STEP-BY-STEP HARDWARE REGISTERS ---
	shift_reg = 0
	decoding_mode = "Searching for Sync"
	high_gcr_bits, low_gcr_bits = [], []
	high_nybble_val, low_nybble_val = None, None
	bit_accumulator, bits_in_accumulator = 0, 0
	is_collecting_low_nybble = False
	byte_index_counter = 0
	
	active_header_record = None
	active_sector_data_pool = None
	current_sector_id = None
	sectors_registry_map = {}
	bit_idx = 0
	current_revolution = 1

	while True:
		stdscr.erase()
		max_y, max_x = stdscr.getmaxyx()
		
		# PANEL SECTION 1: GLOBAL HARDWARE METRICS
		stdscr.addstr(1, 2, "1541 READ-HEAD HARDWARE GCR BITSTREAM EMULATION SIMULATOR", curses.A_BOLD)
		stdscr.addstr(2, 2, f"FILE: {os.path.basename(file_path)}  |  TRACK: {target_track:.1f}  |  TRACK SIZE: {track_len} Bytes", curses.color_pair(1))
		stdscr.addstr(3, 2, "-" * (max_x - 4))
		
		start_view = max(0, bit_idx - 30)
		end_view = min(total_track_bits, bit_idx + 30)
		slider_bits_str = "".join(str(bit_stream_array[i]) for i in range(start_view, end_view))
		
		stdscr.addstr(5, 4, f"... {slider_bits_str} ...")
		marker_x_pos = 4 + 4 + (bit_idx - start_view)
		stdscr.addch(4, marker_x_pos, 'v', curses.color_pair(1) | curses.A_BOLD)
		stdscr.addch(6, marker_x_pos, '^', curses.color_pair(1) | curses.A_BOLD)

		# PANEL SECTION 2: LIVE INTERNAL REGISTERS & NYBBLE MONITORS
		binary_shift_str = f"{shift_reg:010b}"
		stdscr.addstr(8, 2, "DRIVE CONTROLLER WORKSPACE STATUS:")
		stdscr.addstr(9, 4, f"10-BIT SHIFT REGISTER: [ {binary_shift_str} ]")
		
		if shift_reg == 0x3FF or decoding_mode == "Sync Locked":
			stdscr.addstr(9, 32, "** SYNC LOCK ACTIVE **", curses.color_pair(4) | curses.A_BLINK | curses.A_BOLD)
			
		high_bin_str = "".join(str(b) for b in high_gcr_bits).ljust(5, ".") if high_gcr_bits else "....."
		low_bin_str = "".join(str(b) for b in low_gcr_bits).ljust(5, ".") if low_gcr_bits else "....."
		high_hex_str = f"${high_nybble_val:X}" if high_nybble_val is not None else "$."
		low_hex_str = f"${low_nybble_val:X}" if low_nybble_val is not None else "$."
		
		stdscr.addstr(10, 4, f"HIGH NYBBLE GCR:       [ {high_bin_str:<5} ] -> HEX: {high_hex_str}")
		stdscr.addstr(11, 4, f"LOW NYBBLE GCR:        [ {low_bin_str:<5} ] -> HEX: {low_hex_str}")
		
		stdscr.addstr(12, 4, f"CURRENT STATE:         ")
		stdscr.addstr(12, 27, f"{decoding_mode:<22}", curses.A_BOLD | curses.color_pair(1))
		stdscr.addstr(13, 4, f"REVOLUTIONS INDEX:     {current_revolution} / 4  (Bit Offset: {bit_idx} / {total_track_bits})")

		# PANEL SECTION 3: DECODED SECTOR HEADER PROPERTIES (REAL-TIME ACQUISITION CHANNELS)
		stdscr.addstr(15, 2, "LIVE STREAMING SECTOR HEADER RECEPTION WORKSPACE:")
		stdscr.addstr(16, 2, "+" + "-" * 55 + "+", curses.color_pair(2))
		if active_header_record:
			h = active_header_record
			stdscr.addstr(17, 4, f"HEADER BLOCK ID SIGNATURE:  " + (f"${h['id']:02X}  (Standard CBM)" if 'id' in h else "$.."), curses.color_pair(2))
			stdscr.addstr(18, 4, f"HEADER BLOCK CHECKSUM:      " + (f"${h['chk']:02X}" if 'chk' in h else "$.."), curses.color_pair(2))
			stdscr.addstr(19, 4, f"PHYSICAL TRACK NUMBER:      " + (f"Track {h['trk']}" if 'trk' in h else "Track .."), curses.color_pair(2))
			stdscr.addstr(20, 4, f"PHYSICAL SECTOR NUMBER:     " + (f"Sector {h['sec']}" if 'sec' in h else "Sector .."), curses.color_pair(2) | curses.A_BOLD)
			stdscr.addstr(21, 4, f"FORMAT ID WORKSPACE BYTES:  " + (f"${h['f1']:02X} ${h['f2']:02X}" if 'f1' in h and 'f2' in h else "$.. $.."), curses.color_pair(2))
		else:
			for line in range(17, 22):
				stdscr.addstr(line, 4, "| ... Cruising track bitstream channel, awaiting header ... |", curses.A_DIM)
		stdscr.addstr(22, 2, "+" + "-" * 55 + "+", curses.color_pair(2))

		# FIXED REQUIREMENT: Added live "Sectors Found" registry line array output display directly under header frame!
		found_sectors_sorted = sorted(list(sectors_registry_map.keys()))
		found_sectors_str = ", ".join(str(s) for s in found_sectors_sorted) if found_sectors_sorted else "None yet"
		stdscr.addstr(32, 2, "Sectors Found: ", curses.A_BOLD)
		stdscr.addstr(32, 17, found_sectors_str, curses.color_pair(2))

		# PANEL SECTION 4: FULL DATA BLOCKS MATRIX WORKSPACE
		stdscr.addstr(8, 62, "LIVE PERSISTENT SECTOR PAYLOAD DATA COMPILATION CELL:")
		if active_sector_data_pool is not None:
			current_rendering_sec = current_sector_id if current_sector_id is not None else "?"
			stdscr.addstr(9, 62, f"HEX DUMP GRID FOR CURRENT SECTOR CELL: Sector {current_rendering_sec:<2}", curses.A_UNDERLINE)
			for row_idx in range(16):
				offset_addr = row_idx * 16
				stdscr.addstr(11 + row_idx, 62, f"${offset_addr:02X}: ", curses.color_pair(3))
				hex_row_str, ascii_row_str = "", ""
				for col_idx in range(16):
					byte_cell_idx = offset_addr + col_idx
					if byte_cell_idx in active_sector_data_pool:
						b_val = active_sector_data_pool[byte_cell_idx]
						hex_row_str += f"{b_val:02X} "
						ascii_row_str += chr(b_val) if 32 <= b_val <= 126 else "."
					else:
						hex_row_str += ".. "
						ascii_row_str += "."
				stdscr.addstr(11 + row_idx, 67, f"{hex_row_str:<48} |{ascii_row_str}|", curses.color_pair(3))
		else:
			stdscr.addstr(12, 65, "[ PAYLOAD WORKSPACE CLEAR ]", curses.A_DIM)
			stdscr.addstr(14, 65, "Awaiting data block identifier ($07)...", curses.A_DIM)

		stdscr.addstr(max_y - 2, 2, "SIMULATOR COMMANDS: [ANY KEY] = 1 Bit Forward | [S] = Skip 10 Bits (1 Byte) | [Q] = Exit", curses.A_REVERSE)
		stdscr.refresh()
		# (Continued directly inside main_simulation_canvas function scope)
		inp_ch = stdscr.getch()
		if inp_ch in (ord('q'), ord('Q'), 27):
			break

		total_steps_to_execute = 10 if inp_ch in (ord('s'), ord('S')) else 1
		for step in range(total_steps_to_execute):
			if bit_idx >= total_track_bits:
				bit_idx, current_revolution = 0, current_revolution + 1
				if current_revolution > 4: break

			active_bit = bit_stream_array[bit_idx]
			bit_idx += 1
			shift_reg = ((shift_reg << 1) | active_bit) & 0x3FF

			if shift_reg == 0x3FF:
				decoding_mode = "Sync Locked"
				bits_in_accumulator, bit_accumulator = 0, 0
				is_collecting_low_nybble = False
				continue

			if decoding_mode == "Searching for Sync":
				continue

			elif decoding_mode == "Sync Locked":
				if active_bit == 0:
					decoding_mode = "Reading Header"
					bits_in_accumulator, bit_accumulator = 0, 0
					is_collecting_low_nybble = False
					byte_index_counter = 0
					high_gcr_bits, low_gcr_bits = [], []
					high_nybble_val, low_nybble_val = None, None
				else:
					continue

			bit_accumulator = ((bit_accumulator << 1) | active_bit) & 0x1F
			bits_in_accumulator += 1
			if not is_collecting_low_nybble: high_gcr_bits.append(active_bit)
			else: low_gcr_bits.append(active_bit)

			if bits_in_accumulator == 5:
				decoded_nyb = GCR_TO_NYBBLE.get(bit_accumulator, 0)
				if not is_collecting_low_nybble:
					high_nybble_val, is_collecting_low_nybble = decoded_nyb, True
					low_gcr_bits, low_nybble_val = [], None
				else:
					low_nybble_val = decoded_nyb
					current_assembled_byte = (high_nybble_val << 4) | low_nybble_val
					
					if byte_index_counter == 0:
						if current_assembled_byte == 0x08:
							decoding_mode = "Reading Header"
							# FIXED REQUIREMENT: Clear out header area the exact millisecond next header hits!
							active_header_record = {"id": current_assembled_byte}
						elif current_assembled_byte in (0x07, 0xF1):
							# FIXED: Mapped properly to data block identifier, and wipes matrix clean instantly!
							decoding_mode = "Reading Data Identifier"
							active_sector_data_pool = {} 
						else:
							decoding_mode = "Searching for Sync"
					else:
						if decoding_mode == "Reading Header" and active_header_record is not None:
							if byte_index_counter == 1: active_header_record["chk"] = current_assembled_byte
							elif byte_index_counter == 2: 
								active_header_record["sec"] = current_assembled_byte
								current_sector_id = current_assembled_byte
							elif byte_index_counter == 3: active_header_record["trk"] = current_assembled_byte
							elif byte_index_counter == 4: active_header_record["f1"] = current_assembled_byte
							elif byte_index_counter == 5:
								active_header_record["f2"] = current_assembled_byte
								decoding_mode = "Reading Header Gap"
									
						elif decoding_mode == "Reading Header Gap" and byte_index_counter >= 14:
							decoding_mode = "Searching for Sync"
								
						elif decoding_mode == "Reading Data Identifier" and active_sector_data_pool is not None:
							payload_byte_idx = byte_index_counter - 1
							if 0 <= payload_byte_idx <= 255:
								active_sector_data_pool[payload_byte_idx] = current_assembled_byte
							elif payload_byte_idx == 256:
								# Data block complete! Log the successful cache registration
								if current_sector_id is not None:
									sectors_registry_map[current_sector_id] = True
									unique_sectors_cached_count = len(sectors_registry_map)
								decoding_mode = "Searching for Sync"
					
					byte_index_counter += 1
					is_collecting_low_nybble = False
					high_gcr_bits, low_gcr_bits = [], []
				bits_in_accumulator, bit_accumulator = 0, 0
		if current_revolution > 4: break

	stdscr.clear()
	curses.nocbreak()
	stdscr.keypad(False)
	curses.echo()

if __name__ == "__main__":
	target_file, user_track = get_user_inputs_and_validate()
	curses.wrapper(main_simulation_canvas, target_file, user_track)
