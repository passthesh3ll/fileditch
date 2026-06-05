import argparse
import sys
import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from tqdm import tqdm
from colorama import init, Fore, Style
from urllib.parse import quote

init()

def upload_file_worker(file_path, file_index, total_files, proxies, position, is_parallel=False):
    """
    Upload worker for FileDitch using MultipartEncoder (fixes empty file error).
    """
    if not os.path.isfile(file_path):
        tqdm.write(f"{Fore.RED}[!] error: '{file_path}' missing file{Style.RESET_ALL}")
        return None
    
    file_handle = None
    
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            tqdm.write(f"{Fore.RED}[!] error: empty file{Style.RESET_ALL}")
            return None
        
        tqdm.write(f"{Fore.BLUE}[>] [{file_index}/{total_files}] {os.path.basename(file_path)}{Style.RESET_ALL}")
        
        filename = os.path.basename(file_path)
        # FileDitch accepts multipart with ?filename parameter
        safe_filename = quote(filename)
        upload_url = f"https://new.fileditch.com/upload.php?filename={safe_filename}"
        
        file_handle = open(file_path, 'rb')
        
        encoder = MultipartEncoder(
            fields={'file': (filename, file_handle, 'application/octet-stream')}
        )
        
        if is_parallel:
            desc_text = f"{Fore.YELLOW}[>] [{file_index}/{total_files}] uploading{Style.RESET_ALL}"
        else:
            desc_text = f"{Fore.YELLOW}[>] uploading{Style.RESET_ALL}"
        
        pbar = tqdm(
            total=file_size, 
            unit='B', 
            unit_scale=True, 
            desc=desc_text, 
            leave=False,
            position=position,
            file=sys.stdout,
            dynamic_ncols=True
        )
        
        def update_progress(monitor):
            pbar.update(monitor.bytes_read - pbar.n)
        
        progress_encoder = MultipartEncoderMonitor(encoder, update_progress)
        start_time = time.time()
        
        response = requests.post(
            upload_url,
            data=progress_encoder,
            headers={'Content-Type': encoder.content_type},
            timeout=600,
            proxies=proxies
        )
        
        pbar.close()
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                download_link = data.get('url')
                
                if is_parallel:
                    tqdm.write(f"{Fore.GREEN}[+] [{file_index}/{total_files}] link: {download_link} ({elapsed_time:.1f}s){Style.RESET_ALL}")
                else:
                    tqdm.write(f"{Fore.GREEN}[+] link: {download_link} ({elapsed_time:.1f}s){Style.RESET_ALL}")
                
                return {'link': download_link, 'filename': filename, 'path': file_path}
            else:
                error_msg = data.get('error', 'unknown error')
                tqdm.write(f"{Fore.RED}[!] upload rejected: {error_msg}{Style.RESET_ALL}")
                return None
        else:
            error_msg = {
                400: "Empty file or no file sent",
                403: "Blocked file type",
                405: "Wrong HTTP method",
                413: "File exceeds 25GB limit",
                500: "Server error"
            }.get(response.status_code, f"HTTP {response.status_code}")
            
            try:
                data = response.json()
                if 'error' in data:
                    error_msg = data['error']
            except:
                pass
            
            tqdm.write(f"{Fore.RED}[!] error: {error_msg}{Style.RESET_ALL}")
            return None
                
    except Exception as e:
        tqdm.write(f"{Fore.RED}[!] error: {str(e)}{Style.RESET_ALL}")
        return None
        
    finally:
        if file_handle:
            file_handle.close()


def upload_with_retries(path, file_index, total_files, proxies, position, is_parallel=False):
    max_attempts = 3
    
    for attempt in range(1, max_attempts + 1):
        result = upload_file_worker(path, file_index, total_files, proxies, position, is_parallel)
        if result is not None:
            return result
        
        if attempt < max_attempts:
            tqdm.write(f"{Fore.RED}[!] retry in 10s.. [{attempt}/{max_attempts - 1}]{Style.RESET_ALL}")
            time.sleep(10)

    return None


def parallel_upload(files, parallel, wait_time, proxies):
    if not files:
        return []
    
    position_manager = PositionManager(parallel)
    results = []
    results_lock = threading.Lock()
    
    def worker(args):
        idx, file_path = args
        position = position_manager.acquire()
        try:
            result = upload_with_retries(file_path, idx, len(files), proxies, position, is_parallel=True)
            if result:
                with results_lock:
                    results.append(result)
            
            if wait_time > 0 and idx < len(files):
                time.sleep(wait_time)
            return result
        finally:
            position_manager.release(position)
    
    print(f"{Fore.CYAN}[>] starting {len(files)} uploads to FileDitch with {parallel} workers{Style.RESET_ALL}\n")
    
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(worker, (i+1, f)): (i+1, f) for i, f in enumerate(files)}
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                tqdm.write(f"{Fore.RED}[!] worker error: {e}{Style.RESET_ALL}")
    
    return results


class PositionManager:
    def __init__(self, max_positions):
        self.queue = Queue()
        for i in range(max_positions):
            self.queue.put(i)
    
    def acquire(self):
        return self.queue.get()
    
    def release(self, position):
        self.queue.put(position)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="upload files or folders to FileDitch")
    parser.add_argument("path", help="path to the file or folder to upload")
    parser.add_argument("--log", action="store_true", help="save upload links to _links.txt file")
    parser.add_argument("--wait", type=int, default=5, help="seconds to wait between uploads")
    parser.add_argument("--proxy", nargs='?', const='socks5://127.0.0.1:9050', default=None, help="use proxy")
    parser.add_argument("--parallel", type=int, default=1, help="number of parallel uploads")

    args = parser.parse_args()
    
    proxies = None
    if args.proxy is not None:
        proxies = {'http': args.proxy, 'https': args.proxy}
        print(f"{Fore.CYAN}[>] using proxy: {args.proxy}{Style.RESET_ALL}")
    
    upload_results = []
    total_files_count = 0
    
    if os.path.isfile(args.path):
        total_files_count = 1
        single_log_path = None
        if args.log:
            output_dir = os.path.dirname(args.path)
            filename = os.path.basename(args.path)
            single_log_path = os.path.join(output_dir if output_dir else '.', 
                                          f"{os.path.splitext(filename)[0]}_links.txt")
        
        result = upload_with_retries(args.path, 1, 1, proxies, 0, is_parallel=False)
        if result:
            upload_results.append(result)
            if single_log_path:
                try:
                    with open(single_log_path, 'a', encoding='utf-8') as log_file:
                        log_file.write(f"{result['link']}\n")
                except Exception as e:
                    print(f"{Fore.RED}[!] error saving link: {str(e)}{Style.RESET_ALL}")

    elif os.path.isdir(args.path):
        files = sorted([os.path.join(args.path, f) for f in os.listdir(args.path) 
                       if os.path.isfile(os.path.join(args.path, f))], 
                      key=lambda x: os.path.basename(x).lower())
        total_files_count = len(files)
        
        if not files:
            print(f"{Fore.RED}[!] error: no files in folder{Style.RESET_ALL}")
            sys.exit(1)
        
        if args.parallel > 1:
            upload_results = parallel_upload(files, args.parallel, args.wait, proxies)
        else:
            for index, file_path in enumerate(files, 1):
                result = upload_with_retries(file_path, index, len(files), proxies, 0, is_parallel=False)
                if result:
                    upload_results.append(result)
                if index < len(files) and args.wait > 0:
                    print(f"{Fore.YELLOW}[>] waiting {args.wait}s..{Style.RESET_ALL}")
                    time.sleep(args.wait)
        
        if args.log and upload_results:
            folder_path = os.path.normpath(args.path)
            folder_name = os.path.basename(folder_path)
            if not folder_name or folder_name == '.':
                folder_name = os.path.basename(os.getcwd())
            
            parent_dir = os.path.dirname(folder_path) if os.path.dirname(folder_path) else '.'
            folder_log_path = os.path.join(parent_dir, f"{folder_name}_links.txt")
            
            try:
                with open(folder_log_path, 'w', encoding='utf-8') as log_file:
                    for result in upload_results:
                        log_file.write(f"{result['link']} - {result['filename']}\n")
                print(f"{Fore.CYAN}[>] saved {len(upload_results)} links to: {folder_log_path}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[!] error saving links file: {str(e)}{Style.RESET_ALL}")

    else:
        print(f"{Fore.RED}[!] error: '{args.path}' invalid path{Style.RESET_ALL}")
        sys.exit(1)
    
    if upload_results:
        print(f"\n{Fore.YELLOW}[>] uploads finished ({len(upload_results)}/{total_files_count}){Style.RESET_ALL}")
        for result in upload_results:
            print(f"{Fore.GREEN}[+] {result['link']}{Style.RESET_ALL} - {Fore.BLUE}{result['filename']}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}[!] no uploads completed successfully{Style.RESET_ALL}")
        sys.exit(1)
