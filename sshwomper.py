import sys
import json
import os
import stat
import time
import appdirs
import collections
import threading
import re

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QListWidgetItem, QPushButton, QLabel,
                             QMessageBox, QLineEdit, QFormLayout,
                             QTextEdit, QSplitter, QProgressBar, QTabWidget,
                             QMainWindow, QTabBar, QStackedWidget)

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject
from PyQt5.QtGui import QFont, QIcon
import paramiko
from datetime import datetime


class SSHClient:
    """Handles SSH connection and remote operations"""

    DATA_DIR = appdirs.user_data_dir("shhwomper", "shhwomper")
    os.makedirs(DATA_DIR, exist_ok=True)
    SAVE_PATH = os.path.join(DATA_DIR, "saved_clients.json")

    def __init__(self):
        self.ssh_client = None
        self.sftp_client = None
        self.current_path = None
        self.history = collections.deque(maxlen=200)
        self.connection_info = {}
        
        # Interactive shell support
        self.shell = None
        self.shell_thread = None
        self.shell_running = False
        self.output_callbacks = []
        self.shell_buffer = ""

    def connect(self, hostname, username, password=None, port=22):
        """Establish SSH connection"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.connection_info = {
                'hostname': hostname,
                'username': username,
                'port': port
            }

            if password:
                self.connection_info['password'] = password

            # Connect
            if password:
                self.ssh_client.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    password=password,
                    timeout=10
                )
            else:
                self.ssh_client.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    timeout=10
                )

            # Verify connection
            stdin, stdout, stderr = self.ssh_client.exec_command('whoami')
            result = stdout.read().decode().strip()

            if result != username:
                raise Exception("Authentication verification failed")

            self.sftp_client = self.ssh_client.open_sftp()
            self.current_path = self.sftp_client.getcwd() or '/'

            # send a keepalive message every 30 seconds so our session doesnt timeout.
            self.ssh_client.get_transport().set_keepalive(30)

            # Save this client if it's new
            self._save_client(self.connection_info)

            return True

        except Exception as e:
            self.disconnect()
            raise e

    def start_interactive_shell(self):
        """Start an interactive shell session"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        if self.shell_running:
            return  # Already running
        
        try:
            self.shell = self.ssh_client.invoke_shell()
            self.shell.settimeout(0.1)
            self.shell_running = True
            
            # Start shell reading thread
            self.shell_thread = threading.Thread(target=self._shell_reader, daemon=True)
            self.shell_thread.start()
            
            return True
        except Exception as e:
            self.shell_running = False
            raise e

    def stop_interactive_shell(self):
        """Stop the interactive shell session"""
        self.shell_running = False
        if self.shell:
            try:
                self.shell.close()
            except:
                pass
            self.shell = None
        
        if self.shell_thread:
            self.shell_thread.join(timeout=1.0)
            self.shell_thread = None

    def send_to_shell(self, command):
        """Send a command to the interactive shell"""
        if not self.shell or not self.shell_running:
            raise Exception("Interactive shell not running")
        
        try:
            self.shell.send(command + '\n')
            self.history.append(command)
        except Exception as e:
            raise Exception(f"Failed to send command: {e}")

    def add_output_callback(self, callback):
        """Add a callback function to receive shell output"""
        self.output_callbacks.append(callback)

    def remove_output_callback(self, callback):
        """Remove an output callback"""
        if callback in self.output_callbacks:
            self.output_callbacks.remove(callback)

    def _shell_reader(self):
        """Background thread to read shell output"""
        while self.shell_running and self.shell:
            try:
                if self.shell.recv_ready():
                    output = self.shell.recv(1024).decode('utf-8', errors='ignore')
                    # Filter ANSI escape sequences
                    filtered_output = self._filter_ansi(output)
                    
                    # Add to buffer and history
                    self.shell_buffer += filtered_output
                    for line in filtered_output.splitlines():
                        if line.strip():
                            self.history.append(line.strip())
                    
                    # Call output callbacks
                    for callback in self.output_callbacks:
                        try:
                            callback(filtered_output)
                        except Exception as e:
                            print(f"Output callback error: {e}")
                
                time.sleep(0.01)  # Small delay to prevent excessive CPU usage
                
            except Exception as e:
                if "timed out" not in str(e).lower():
                    print(f"Shell reader error: {e}")
                    break

    def _filter_ansi(self, text):
        """Filter ANSI escape sequences from text"""
        ansi_escape = re.compile(r'\x1b(?:\[[?0-9;]*[a-zA-Z]|\][0-9];.*?\x07|[()][AB012])')
        return ansi_escape.sub('', text)

    def get_shell_buffer(self):
        """Get the current shell output buffer"""
        return self.shell_buffer

    def clear_shell_buffer(self):
        """Clear the shell output buffer"""
        self.shell_buffer = ""

    def is_shell_running(self):
        """Check if interactive shell is running"""
        return self.shell_running and self.shell is not None

    @classmethod
    def _save_client(cls, info):
        """Save client info to disk if it's not already saved"""
        existing = cls.get_saved_clients()

        # Don't save password field for matching
        compare_info = {k: v for k, v in info.items() if k != 'password'}
        if compare_info not in [{k: v for k, v in c.items() if k != 'password'} for c in existing]:
            existing.append(info)
            try:
                with open(cls.SAVE_PATH, 'w') as f:
                    json.dump(existing, f, indent=2)
            except Exception as e:
                print(f"Failed to save client: {e}")

    @classmethod
    def get_saved_clients(cls):
        """Retrieve all saved SSH clients"""
        if not os.path.exists(cls.SAVE_PATH):
            return []
        try:
            with open(cls.SAVE_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load clients: {e}")
            return []
    
    @classmethod
    def start_saved_client(cls, connection_info):
        """Creates a SSHClient for all saved clients"""
        cl = SSHClient()
        cl.connect(
            connection_info["hostname"], 
            connection_info["username"],
            connection_info.get("password", None),
            connection_info["port"],
        )
        return cl

    def disconnect(self):
        """Close SSH and SFTP connections"""
        # Stop interactive shell first
        self.stop_interactive_shell()
        
        if self.sftp_client:
            try:
                self.sftp_client.close()
            except:
                pass
            self.sftp_client = None
        
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None
    
    def execute_user_command(self, command):
        """
        Executes a user-command and returns output, error, and return code.
        This will put the output in the shell
        """
        self.history.append(command)
        stdout, stderr, return_code = self.execute_command(command)
        for s in stdout.splitlines():
            self.history.append(s)
        return stdout, stderr, return_code
    
    def get_user_command_history(self):
        return self.history

    def execute_command(self, command):
        """Execute a command and return output, error, and return code"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            
            stdout_data = stdout.read().decode().strip()
            stderr_data = stderr.read().decode().strip()
            return_code = stdout.channel.recv_exit_status()
            
            return stdout_data, stderr_data, return_code
            
        except Exception as e:
            return "", str(e), 1

    def list_directory(self, path=None):
        """List directory contents using ls command"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        target_path = path or self.current_path
        
        # Use ls -la for detailed listing
        command = f"ls -la '{target_path}'"
        stdout, stderr, return_code = self.execute_command(command)
        
        if return_code != 0:
            raise Exception(f"Failed to list directory: {stderr}")
        
        # Parse ls output
        items = []
        lines = stdout.split('\n')
        
        for line in lines[1:]:  # Skip first line (total)
            if not line.strip():
                continue
            
            # Parse ls -la output
            parts = line.split()
            if len(parts) < 9:
                continue
            
            permissions = parts[0]
            size = parts[4]
            name = ' '.join(parts[8:])  # Handle names with spaces
            
            # Skip current and parent directory entries
            if name in ['.', '..']:
                continue
            
            # Determine file type
            if permissions.startswith('d'):
                file_type = 'directory'
            elif permissions.startswith('l'):
                file_type = 'link'
            elif 'x' in permissions:
                file_type = 'executable'
            else:
                file_type = 'file'
            
            items.append({
                'name': name,
                'type': file_type,
                'permissions': permissions,
                'size': size,
                'raw_line': line
            })
        
        return items
    
    def change_directory(self, path):
        """Change current directory using cd command"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        # Handle relative paths
        if path == '..':
            new_path = os.path.dirname(self.current_path.rstrip('/'))
            if not new_path:
                new_path = '/'
        elif path.startswith('/'):
            new_path = path
        else:
            new_path = os.path.join(self.current_path, path)
        
        # Normalize path
        new_path = os.path.normpath(new_path).replace('\\', '/')
        if not new_path.startswith('/'):
            new_path = '/' + new_path
        
        # Test directory access
        command = f"cd '{new_path}' && pwd"
        stdout, stderr, return_code = self.execute_command(command)
        
        if return_code != 0:
            raise Exception(f"Cannot access directory: {stderr}")
        
        # Update current path
        self.current_path = stdout.strip()
        
        # Also update SFTP client path
        if self.sftp_client:
            try:
                self.sftp_client.chdir(self.current_path)
            except:
                pass  # SFTP path update is not critical
        
        return self.current_path
    
    def get_processes(self):
        """Get top CPU-consuming processes"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        command = "ps aux --sort=-%cpu | head -n 15"
        stdout, stderr, return_code = self.execute_command(command)
        
        if return_code != 0:
            raise Exception(f"Failed to get processes: {stderr}")
        
        processes = []
        lines = stdout.split('\n')
        
        # Skip header line
        for line in lines[1:]:
            if not line.strip():
                continue
            
            # Parse ps aux output
            parts = line.split(None, 10)  # Split on whitespace, max 11 parts
            if len(parts) < 11:
                continue

            try:
                process = {
                    'user': parts[0],
                    'pid': parts[1],
                    'cpu': float(parts[2]),
                    'mem': float(parts[3]),
                    'vsz': parts[4],
                    'rss': parts[5],
                    'tty': parts[6],
                    'stat': parts[7],
                    'start': parts[8],
                    'time': parts[9],
                    'command': parts[10]
                }
                processes.append(process)
            except (ValueError, IndexError):
                continue
        
        return processes
    
    def get_home_directory(self):
        """Get user's home directory"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        stdout, stderr, return_code = self.execute_command('echo $HOME')
        if return_code == 0 and stdout:
            return stdout.strip()
        
        # Fallback
        return f"/home/{self.connection_info.get('username', '')}"
    
    def get_current_path(self):
        """Get current working directory"""
        return self.current_path
    
    def is_connected(self):
        """Check if SSH connection is active"""
        return self.ssh_client is not None and self.ssh_client.get_transport() is not None




class ShellReaderThread(QThread):
    """QThread for reading shell output in background"""
    
    # Signals for communicating with main thread
    output_received = pyqtSignal(str)  # Raw output
    filtered_output_received = pyqtSignal(str)  # Filtered output
    error_occurred = pyqtSignal(str)  # Error messages
    
    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self.shell = shell
        self.running = False
        self._ansi_escape = re.compile(r'\x1b(?:\[[?0-9;]*[a-zA-Z]|\][0-9];.*?\x07|[()][AB012])')
    
    def run(self):
        """Main thread execution"""
        self.running = True
        
        while self.running and self.shell:
            try:
                if self.shell.recv_ready():
                    output = self.shell.recv(1024).decode('utf-8', errors='ignore')
                    
                    # Emit raw output
                    self.output_received.emit(output)
                    
                    # Filter ANSI escape sequences and emit filtered output
                    filtered_output = self._filter_ansi(output)
                    if filtered_output:
                        self.filtered_output_received.emit(filtered_output)
                
                # Small delay to prevent excessive CPU usage
                self.msleep(10)  # QThread's msleep method
                
            except Exception as e:
                if "timed out" not in str(e).lower():
                    self.error_occurred.emit(f"Shell reader error: {e}")
                    break
    
    def stop(self):
        """Stop the thread gracefully"""
        self.running = False
    
    def _filter_ansi(self, text):
        """Filter ANSI escape sequences from text"""
        return self._ansi_escape.sub('', text)


class SSHClient(QObject):
    """Handles SSH connection and remote operations using QThread"""
    
    # Signals for shell events
    shell_output = pyqtSignal(str)  # Filtered shell output
    shell_error = pyqtSignal(str)   # Shell errors
    shell_started = pyqtSignal()    # Shell session started
    shell_stopped = pyqtSignal()    # Shell session stopped
    
    DATA_DIR = appdirs.user_data_dir("shhwomper", "shhwomper")
    os.makedirs(DATA_DIR, exist_ok=True)
    SAVE_PATH = os.path.join(DATA_DIR, "saved_clients.json")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ssh_client = None
        self.sftp_client = None
        self.current_path = None
        self.history = collections.deque(maxlen=200)
        self.connection_info = {}
        
        # Interactive shell support with QThread
        self.shell = None
        self.shell_thread = None
        self.shell_running = False
        self.shell_buffer = ""
        
        # Output callbacks (kept for backward compatibility)
        self.output_callbacks = []

    def connect(self, hostname, username, password=None, port=22):
        """Establish SSH connection"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.connection_info = {
                'hostname': hostname,
                'username': username,
                'port': port
            }

            if password:
                self.connection_info['password'] = password

            # Connect
            if password:
                self.ssh_client.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    password=password,
                    timeout=10
                )
            else:
                self.ssh_client.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    timeout=10
                )

            # Verify connection
            stdin, stdout, stderr = self.ssh_client.exec_command('whoami')
            result = stdout.read().decode().strip()

            if result != username:
                raise Exception("Authentication verification failed")

            self.sftp_client = self.ssh_client.open_sftp()
            self.current_path = self.sftp_client.getcwd() or '/'

            # Send a keepalive message every 30 seconds so our session doesn't timeout
            self.ssh_client.get_transport().set_keepalive(30)

            # Save this client if it's new
            self._save_client(self.connection_info)

            return True

        except Exception as e:
            self.disconnect()
            raise e

    def start_interactive_shell(self):
        """Start an interactive shell session using QThread"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        if self.shell_running:
            return  # Already running
        
        try:
            self.shell = self.ssh_client.invoke_shell()
            self.shell.settimeout(0.1)
            self.shell_running = True
            
            # Create and start shell reading thread
            self.shell_thread = ShellReaderThread(self.shell, self)
            
            # Connect thread signals to our methods
            self.shell_thread.filtered_output_received.connect(self._on_shell_output)
            self.shell_thread.error_occurred.connect(self._on_shell_error)
            self.shell_thread.finished.connect(self._on_shell_thread_finished)
            
            # Start the thread
            self.shell_thread.start()
            
            # Emit signal that shell started
            self.shell_started.emit()
            
            return True
            
        except Exception as e:
            self.shell_running = False
            raise e

    def stop_interactive_shell(self):
        """Stop the interactive shell session"""
        self.shell_running = False
        
        # Stop the thread gracefully
        if self.shell_thread and self.shell_thread.isRunning():
            self.shell_thread.stop()
            self.shell_thread.wait(1000)  # Wait up to 1 second for thread to finish
            
            if self.shell_thread.isRunning():
                self.shell_thread.terminate()  # Force terminate if still running
                self.shell_thread.wait()
        
        # Clean up shell
        if self.shell:
            try:
                self.shell.close()
            except:
                pass
            self.shell = None
        
        self.shell_thread = None
        
        # Emit signal that shell stopped
        self.shell_stopped.emit()

    def send_to_shell(self, command):
        """Send a command to the interactive shell"""
        if not self.shell or not self.shell_running:
            raise Exception("Interactive shell not running")
        
        try:
            self.shell.send(command + '\n')
            self.history.append(command)
        except Exception as e:
            raise Exception(f"Failed to send command: {e}")

    def add_output_callback(self, callback):
        """Add a callback function to receive shell output (backward compatibility)"""
        self.output_callbacks.append(callback)

    def remove_output_callback(self, callback):
        """Remove an output callback (backward compatibility)"""
        if callback in self.output_callbacks:
            self.output_callbacks.remove(callback)

    def _on_shell_output(self, output):
        """Handle shell output from QThread"""
        # Add to buffer and history
        self.shell_buffer += output
        for line in output.splitlines():
            if line.strip():
                self.history.append(line.strip())
        
        # Call legacy output callbacks for backward compatibility
        for callback in self.output_callbacks:
            try:
                callback(output)
            except Exception as e:
                self.shell_error.emit(f"Output callback error: {e}")
        
        # Emit signal for Qt-based handlers
        self.shell_output.emit(output)

    def _on_shell_error(self, error):
        """Handle shell errors from QThread"""
        self.shell_error.emit(error)

    def _on_shell_thread_finished(self):
        """Handle shell thread finished"""
        if self.shell_running:
            # Thread finished unexpectedly
            self.shell_running = False
            self.shell_stopped.emit()

    def get_shell_buffer(self):
        """Get the current shell output buffer"""
        return self.shell_buffer

    def clear_shell_buffer(self):
        """Clear the shell output buffer"""
        self.shell_buffer = ""

    def is_shell_running(self):
        """Check if interactive shell is running"""
        return self.shell_running and self.shell is not None

    @classmethod
    def _save_client(cls, info):
        """Save client info to disk if it's not already saved"""
        existing = cls.get_saved_clients()

        # Don't save password field for matching
        compare_info = {k: v for k, v in info.items() if k != 'password'}
        if compare_info not in [{k: v for k, v in c.items() if k != 'password'} for c in existing]:
            existing.append(info)
            try:
                with open(cls.SAVE_PATH, 'w') as f:
                    json.dump(existing, f, indent=2)
            except Exception as e:
                print(f"Failed to save client: {e}")

    @classmethod
    def get_saved_clients(cls):
        """Retrieve all saved SSH clients"""
        if not os.path.exists(cls.SAVE_PATH):
            return []
        try:
            with open(cls.SAVE_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load clients: {e}")
            return []
    
    @classmethod
    def start_saved_client(cls, connection_info, parent=None):
        """Creates a SSHClient for all saved clients"""
        cl = cls(parent)
        cl.connect(
            connection_info["hostname"], 
            connection_info["username"],
            connection_info.get("password", None),
            connection_info["port"],
        )
        return cl

    def disconnect(self):
        """Close SSH and SFTP connections"""
        # Stop interactive shell first
        self.stop_interactive_shell()
        
        if self.sftp_client:
            try:
                self.sftp_client.close()
            except:
                pass
            self.sftp_client = None
        
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None
    
    def execute_user_command(self, command):
        """
        Executes a user-command and returns output, error, and return code.
        This will put the output in the shell
        """
        self.history.append(command)
        stdout, stderr, return_code = self.execute_command(command)
        for s in stdout.splitlines():
            self.history.append(s)
        return stdout, stderr, return_code
    
    def get_user_command_history(self):
        return self.history

    def execute_command(self, command):
        """Execute a command and return output, error, and return code"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            
            stdout_data = stdout.read().decode().strip()
            stderr_data = stderr.read().decode().strip()
            return_code = stdout.channel.recv_exit_status()
            
            return stdout_data, stderr_data, return_code
            
        except Exception as e:
            return "", str(e), 1

    def list_directory(self, path=None):
        """List directory contents using ls command"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        target_path = path or self.current_path
        
        # Use ls -la for detailed listing
        command = f"ls -la '{target_path}'"
        stdout, stderr, return_code = self.execute_command(command)
        
        if return_code != 0:
            raise Exception(f"Failed to list directory: {stderr}")
        
        # Parse ls output
        items = []
        lines = stdout.split('\n')
        
        for line in lines[1:]:  # Skip first line (total)
            if not line.strip():
                continue
            
            # Parse ls -la output
            parts = line.split()
            if len(parts) < 9:
                continue
            
            permissions = parts[0]
            size = parts[4]
            name = ' '.join(parts[8:])  # Handle names with spaces
            
            # Skip current and parent directory entries
            if name in ['.', '..']:
                continue
            
            # Determine file type
            if permissions.startswith('d'):
                file_type = 'directory'
            elif permissions.startswith('l'):
                file_type = 'link'
            elif 'x' in permissions:
                file_type = 'executable'
            else:
                file_type = 'file'
            
            items.append({
                'name': name,
                'type': file_type,
                'permissions': permissions,
                'size': size,
                'raw_line': line
            })
        
        return items
    
    def change_directory(self, path):
        """Change current directory using cd command"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        # Handle relative paths
        if path == '..':
            new_path = os.path.dirname(self.current_path.rstrip('/'))
            if not new_path:
                new_path = '/'
        elif path.startswith('/'):
            new_path = path
        else:
            new_path = os.path.join(self.current_path, path)
        
        # Normalize path
        new_path = os.path.normpath(new_path).replace('\\', '/')
        if not new_path.startswith('/'):
            new_path = '/' + new_path
        
        # Test directory access
        command = f"cd '{new_path}' && pwd"
        stdout, stderr, return_code = self.execute_command(command)
        
        if return_code != 0:
            raise Exception(f"Cannot access directory: {stderr}")
        
        # Update current path
        self.current_path = stdout.strip()
        
        # Also update SFTP client path
        if self.sftp_client:
            try:
                self.sftp_client.chdir(self.current_path)
            except:
                pass  # SFTP path update is not critical
        
        return self.current_path
    
    def get_processes(self):
        """Get top CPU-consuming processes"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        command = "ps aux --sort=-%cpu | head -n 15"
        stdout, stderr, return_code = self.execute_command(command)
        
        if return_code != 0:
            raise Exception(f"Failed to get processes: {stderr}")
        
        processes = []
        lines = stdout.split('\n')
        
        # Skip header line
        for line in lines[1:]:
            if not line.strip():
                continue
            
            # Parse ps aux output
            parts = line.split(None, 10)  # Split on whitespace, max 11 parts
            if len(parts) < 11:
                continue

            try:
                process = {
                    'user': parts[0],
                    'pid': parts[1],
                    'cpu': float(parts[2]),
                    'mem': float(parts[3]),
                    'vsz': parts[4],
                    'rss': parts[5],
                    'tty': parts[6],
                    'stat': parts[7],
                    'start': parts[8],
                    'time': parts[9],
                    'command': parts[10]
                }
                processes.append(process)
            except (ValueError, IndexError):
                continue
        
        return processes
    
    def get_home_directory(self):
        """Get user's home directory"""
        if not self.ssh_client:
            raise Exception("Not connected to SSH server")
        
        stdout, stderr, return_code = self.execute_command('echo $HOME')
        if return_code == 0 and stdout:
            return stdout.strip()
        
        # Fallback
        return f"/home/{self.connection_info.get('username', '')}"
    
    def get_current_path(self):
        """Get current working directory"""
        return self.current_path
    
    def is_connected(self):
        """Check if SSH connection is active"""
        return self.ssh_client is not None and self.ssh_client.get_transport() is not None




class SSHLoginWidget(QWidget):
    """Widget for SSH connection setup (embedded in tab)"""
    
    connection_successful = pyqtSignal(object)  # Signal to emit SSH client on success
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        # Title
        title_label = QLabel('SSHWOMPER')
        title_label.setStyleSheet('font-size: 16px; font-weight: bold; margin-bottom: 20px;')
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Form layout for inputs
        form_widget = QWidget()
        form_layout = QFormLayout()
        
        # Hostname input
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText('hostname or IP address')
        self.hostname_input.setFixedWidth(250)
        form_layout.addRow('Hostname:', self.hostname_input)
        
        # Username input
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('username (e.g. root)')
        self.username_input.setFixedWidth(250)
        form_layout.addRow('Username:', self.username_input)
        
        # Password input
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText('password (optional)')
        self.password_input.setFixedWidth(250)
        form_layout.addRow('Password:', self.password_input)
        
        # Port input
        self.port_input = QLineEdit()
        self.port_input.setText('22')
        self.port_input.setPlaceholderText('22')
        self.port_input.setFixedWidth(250)
        form_layout.addRow('Port:', self.port_input)
        
        form_widget.setLayout(form_layout)
        layout.addWidget(form_widget)
        layout.setAlignment(form_widget, Qt.AlignCenter)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(250)
        layout.addWidget(self.progress_bar)
        
        # Connect button
        self.connect_button = QPushButton("Connect")
        self.connect_button.setFixedWidth(250)
        self.connect_button.clicked.connect(self.attempt_connection)
        layout.addWidget(self.connect_button)
        
        self.setLayout(layout)
        
        # Connect Enter key from any field
        self.hostname_input.returnPressed.connect(self.attempt_connection)
        self.username_input.returnPressed.connect(self.attempt_connection)
        self.password_input.returnPressed.connect(self.attempt_connection)
        self.port_input.returnPressed.connect(self.attempt_connection)
    
    def attempt_connection(self):
        """Attempt SSH connection"""
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        port = int(self.port_input.text().strip() or '22')
        
        if not hostname or not username:
            QMessageBox.warning(self, 'Error', 'Please enter both hostname and username')
            return
        
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.connect_button.setEnabled(False)
        QApplication.processEvents()
        
        try:
            # Create and test SSH connection
            ssh_client = SSHClient()
            ssh_client.connect(hostname, username, password if password else None, port)
            
            # Emit success signal with SSH client
            self.connection_successful.emit(ssh_client)
            
        except paramiko.AuthenticationException:
            QMessageBox.critical(self, 'Authentication Failed', 'Invalid username or password.')
        except paramiko.SSHException as e:
            QMessageBox.critical(self, 'SSH Error', f'SSH connection failed:\n{str(e)}')
        except Exception as e:
            QMessageBox.critical(self, 'Connection Failed', f'Failed to connect:\n{str(e)}')
        finally:
            # Hide progress
            self.progress_bar.setVisible(False)
            self.connect_button.setEnabled(True)





class ProcessExplorer(QWidget):
    def __init__(self, ssh_client):
        super().__init__()
        self.ssh_client = ssh_client
        self.init_ui()
        self.refresh_processes()
    
    def init_ui(self):
        main_layout = QVBoxLayout()

        top_bar = QHBoxLayout()

        conn_info = self.ssh_client.connection_info
        connection_text = f'Connected to: {conn_info["username"]}@{conn_info["hostname"]}:{conn_info["port"]}'
        connection_label = QLabel(connection_text)
        connection_label.setStyleSheet('color: #2e7d32; font-weight: bold; font-size: 11px;')

        self.process_count_label = QLabel("Processes: 0")
        self.process_count_label.setStyleSheet("font-size: 11px; color: #555; padding-left: 15px;")

        top_bar.addWidget(connection_label)
        top_bar.addWidget(self.process_count_label)

        nav_layout = QHBoxLayout()
        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.clicked.connect(self.refresh_processes)
        self.kill_button = QPushButton("❌ Kill Process")
        self.kill_button.clicked.connect(self.kill_selected_process)
        self.kill_button.setEnabled(False)
        self.killall_button = QPushButton("💀 Kill All by Name")
        self.killall_button.clicked.connect(self.kill_all_by_name)
        self.killall_button.setEnabled(False)
        self.disconnect_button = QPushButton("🔌 Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect)
        
        nav_layout.addWidget(self.refresh_button)
        nav_layout.addWidget(self.kill_button)
        nav_layout.addWidget(self.killall_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.disconnect_button)
        
        self.process_list = QListWidget()
        self.process_list.itemSelectionChanged.connect(self.on_selection_changed)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by name:"))
        self.filter_input = QLineEdit()
        self.filter_input.textChanged.connect(self.filter_processes)
        self.filter_input.setPlaceholderText("Enter process name to filter...")
        filter_layout.addWidget(self.filter_input)
        
        main_layout.addLayout(top_bar, stretch=1)
        main_layout.addLayout(nav_layout, stretch=1)
        main_layout.addWidget(self.process_list, stretch=12)
        main_layout.addLayout(filter_layout, stretch=1)
        
        self.setLayout(main_layout)
        
        conn_info = self.ssh_client.connection_info
        connection_text = f'{conn_info["username"]}@{conn_info["hostname"]}:{conn_info["port"]}'
    
    def refresh_processes(self):
        try:
            self.process_list.clear()
            
            processes = self.ssh_client.get_processes()
            self.all_processes = processes
            
            self.populate_process_list(processes)
            
            self.process_count_label.setText(f"Processes: {len(processes)}")
            
        except Exception as e:
            error_msg = f"Failed to get processes: {str(e)}"
            QMessageBox.warning(self, "Error", error_msg)
    
    def populate_process_list(self, processes):
        self.process_list.clear()
        
        for proc in processes:
            cpu_bar = "█" * int(proc['cpu'] / 10) if proc['cpu'] > 0 else ""
            mem_bar = "█" * int(proc['mem'] / 10) if proc['mem'] > 0 else ""
            
            item_text = f"PID: {proc['pid']:<8} CPU: {proc['cpu']:<5.1f}% {cpu_bar:<10} MEM: {proc['mem']:<5.1f}% {mem_bar:<10} USER: {proc['user']:<10} CMD: {proc['command'][:50]}"
            
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.UserRole, proc)
            list_item.setFont(QFont('Courier', 9))
            
            if proc['cpu'] > 50:
                list_item.setBackground(Qt.red)
            elif proc['cpu'] > 20:
                list_item.setBackground(Qt.yellow)
            
            self.process_list.addItem(list_item)
    
    def filter_processes(self):
        filter_text = self.filter_input.text().lower()
        if not hasattr(self, 'all_processes'):
            return
        
        if not filter_text:
            filtered_processes = self.all_processes
        else:
            filtered_processes = [p for p in self.all_processes if filter_text in p['command'].lower()]
        
        self.populate_process_list(filtered_processes)
    
    def on_selection_changed(self):
        selected_items = self.process_list.selectedItems()
        self.kill_button.setEnabled(len(selected_items) > 0)
        self.killall_button.setEnabled(len(selected_items) > 0)
    
    def kill_selected_process(self):
        selected_items = self.process_list.selectedItems()
        if not selected_items:
            return
        
        process_data = selected_items[0].data(Qt.UserRole)
        pid = process_data['pid']
        command = process_data['command']
        
        reply = QMessageBox.question(
            self, 
            'Confirm Kill Process',
            f'Are you sure you want to kill process?\n\nPID: {pid}\nCommand: {command}',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                stdout, stderr, return_code = self.ssh_client.execute_command(f'kill {pid}')
                
                if return_code == 0:
                    self.refresh_processes()
                else:
                    error_msg = f"Failed to kill process {pid}: {stderr}"
                    QMessageBox.warning(self, "Kill Failed", error_msg)
                    
            except Exception as e:
                error_msg = f"Error killing process {pid}: {str(e)}"
                QMessageBox.warning(self, "Error", error_msg)
    
    def kill_all_by_name(self):
        selected_items = self.process_list.selectedItems()
        if not selected_items:
            return
        
        process_data = selected_items[0].data(Qt.UserRole)
        command_name = process_data['command'].split()[0]
        
        matching_processes = [p for p in self.all_processes if command_name in p['command']]
        
        reply = QMessageBox.question(
            self,
            'Confirm Kill All Processes',
            f'Are you sure you want to kill ALL processes matching "{command_name}"?\n\n{len(matching_processes)} processes will be killed.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            killed_count = 0
            for proc in matching_processes:
                try:
                    stdout, stderr, return_code = self.ssh_client.execute_command(f'kill {proc["pid"]}')
                    if return_code == 0:
                        killed_count += 1
                except:
                    pass
            
            self.refresh_processes()
    
    def disconnect(self):
        self.parent().parent().parent().disconnect_tab(self)




class DirectoryExplorer(QWidget):
    """Main directory exploration interface"""
    
    def __init__(self, ssh_client):
        super().__init__()
        self.ssh_client = ssh_client
        self.init_ui()
        self.go_home()
    
    def init_ui(self):
        # Main layout
        main_layout = QVBoxLayout()

        # Top bar: connection info + path
        top_bar = QHBoxLayout()

        conn_info = self.ssh_client.connection_info
        connection_text = f'Connected to: {conn_info["username"]}@{conn_info["hostname"]}:{conn_info["port"]}'
        connection_label = QLabel(connection_text)
        connection_label.setStyleSheet('color: #2e7d32; font-weight: bold; font-size: 11px;')

        self.path_label = QLabel(f"Current Path: {self.ssh_client.get_current_path()}")
        self.path_label.setStyleSheet("font-size: 11px; color: #555; padding-left: 15px;")

        top_bar.addWidget(connection_label)
        top_bar.addWidget(self.path_label)
        top_bar.addStretch()
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.go_back)
        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.clicked.connect(self.refresh_directory)
        self.home_button = QPushButton("🏠 Home")
        self.home_button.clicked.connect(self.go_home)
        self.root_button = QPushButton("/ Root")
        self.root_button.clicked.connect(self.go_root)
        self.disconnect_button = QPushButton("🔌 Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect)
        
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.refresh_button)
        nav_layout.addWidget(self.home_button)
        nav_layout.addWidget(self.root_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.disconnect_button)
        
        # Create splitter for directory list and command output
        splitter = QSplitter(Qt.Horizontal)
        
        # Directory listing
        self.dir_list = QListWidget()
        self.dir_list.itemDoubleClicked.connect(self.item_double_clicked)
        splitter.addWidget(self.dir_list)
        
        # Manual path input
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Go to path:"))
        self.path_input = QLineEdit()
        self.path_input.returnPressed.connect(self.navigate_to_path)
        self.go_button = QPushButton("Go")
        self.go_button.clicked.connect(self.navigate_to_path)
        
        input_layout.addWidget(self.path_input)
        input_layout.addWidget(self.go_button)
        
        # Add all layouts to main layout
        main_layout.addLayout(top_bar, stretch=1)
        main_layout.addLayout(nav_layout, stretch=1)
        main_layout.addWidget(splitter, stretch=12)
        main_layout.addLayout(input_layout, stretch=1)
        
        self.setLayout(main_layout)
        
        # Log initial connection
        conn_info = self.ssh_client.connection_info
        connection_text = f'{conn_info["username"]}@{conn_info["hostname"]}:{conn_info["port"]}'
    
    def log_activity(self, message):
        """Log activity to the output area"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_text.append(f"[{timestamp}] {message}")
        
        # Auto-scroll to bottom
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def refresh_directory(self):
        """Refresh the directory listing"""
        try:
            self.dir_list.clear()
            current_path = self.ssh_client.get_current_path()
            
            # Update path label
            self.path_label.setText(f"Current Path: {current_path}")
            
            # Get directory listing
            items = self.ssh_client.list_directory()
            
            # Add parent directory if not at root
            if current_path != '/':
                parent_item = QListWidgetItem("📁 .. (Parent Directory)")
                parent_item.setData(Qt.UserRole, ('directory', '..'))
                self.dir_list.addItem(parent_item)
            
            # Sort items: directories first, then files
            directories = [item for item in items if item['type'] == 'directory']
            files = [item for item in items if item['type'] != 'directory']
            
            # Add directories
            for item in sorted(directories, key=lambda x: x['name'].lower()):
                list_item = QListWidgetItem(f"📁 {item['name']}")
                list_item.setData(Qt.UserRole, ('directory', item['name']))
                self.dir_list.addItem(list_item)
            
            # Add files
            for item in sorted(files, key=lambda x: x['name'].lower()):
                if item['type'] == 'link':
                    icon = "🔗"
                elif item['type'] == 'executable':
                    icon = "⚙️"
                else:
                    icon = "📄"
                
                # Format size
                size_str = self.format_file_size(item['size'])
                item_text = f"{icon} {item['name']} ({size_str})"
                
                list_item = QListWidgetItem(item_text)
                list_item.setData(Qt.UserRole, (item['type'], item['name']))
                self.dir_list.addItem(list_item)
            
        except Exception as e:
            error_msg = f"Failed to list directory: {str(e)}"
            QMessageBox.warning(self, "Error", error_msg)
    
    def format_file_size(self, size_str):
        """Format file size in human readable format"""
        try:
            size_bytes = int(size_str)
            if size_bytes == 0:
                return "0B"
            
            size_names = ["B", "KB", "MB", "GB"]
            i = 0
            while size_bytes >= 1024 and i < len(size_names) - 1:
                size_bytes /= 1024.0
                i += 1
            
            return f"{size_bytes:.1f}{size_names[i]}"
        except ValueError:
            return size_str
    
    def item_double_clicked(self, item):
        """Handle double-click on directory items"""
        item_type, name = item.data(Qt.UserRole)
        
        if item_type == 'directory':
            self.navigate_to_directory(name)
    
    def navigate_to_directory(self, dir_name):
        """Navigate to a directory"""
        try:
            new_path = self.ssh_client.change_directory(dir_name)
            self.refresh_directory()
            
        except Exception as e:
            error_msg = f"Cannot access directory '{dir_name}': {str(e)}"
            QMessageBox.warning(self, "Navigation Error", error_msg)
    
    def go_back(self):
        """Go to parent directory"""
        current_path = self.ssh_client.get_current_path()
        if current_path != '/':
            self.navigate_to_directory('..')
    
    def go_home(self):
        """Go to user home directory"""
        try:
            home_path = self.ssh_client.get_home_directory()
            self.ssh_client.change_directory(home_path)
            self.refresh_directory()
        except Exception as e:
            self.refresh_directory()
    
    def go_root(self):
        """Go to root directory"""
        try:
            self.ssh_client.change_directory('/')
            self.refresh_directory()
        except Exception as e:
            error_msg = f"Cannot access root directory: {str(e)}"
            QMessageBox.warning(self, "Navigation Error", error_msg)
    
    def navigate_to_path(self):
        """Navigate to manually entered path"""
        path = self.path_input.text().strip()
        if not path:
            return
        
        try:
            new_path = self.ssh_client.change_directory(path)
            self.path_input.clear()
            self.refresh_directory()
        except Exception as e:
            error_msg = f"Cannot access path '{path}': {str(e)}"
            QMessageBox.warning(self, "Path Error", error_msg)

    def disconnect(self):
        """Signal parent to disconnect this tab"""
        # This will be handled by the parent MainWindow
        self.parent().parent().parent().disconnect_tab(self)






from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QLabel
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QTextCursor


class CommandLineWidget(QWidget):
    def __init__(self, ssh_client):
        super().__init__()
        self.ssh_client = ssh_client
        self.command_buffer = ""
        self.init_ui()
        
        # Start interactive shell
        try:
            self.ssh_client.start_interactive_shell()
            self.ssh_client.add_output_callback(self.append_output)
        except Exception as e:
            self.append_output(f"Failed to start interactive shell: {str(e)}\n")
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create terminal text area
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)  # Prevent direct editing
        self.terminal.setFont(QFont("Courier", 10))
        self.terminal.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: none;
                padding: 5px;
            }
        """)
        
        layout.addWidget(self.terminal)
        self.setLayout(layout)
        
        # Set focus to terminal
        self.terminal.setFocus()
        
        # Install event filter to capture key presses
        self.terminal.installEventFilter(self)
    
    def append_output(self, text):
        """Handle output from the interactive shell"""
        # Temporarily allow editing to insert text
        self.terminal.setReadOnly(False)
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.terminal.setTextCursor(cursor)
        self.terminal.ensureCursorVisible()
        # Set back to read-only
        self.terminal.setReadOnly(True)
    
    def eventFilter(self, obj, event):
        if obj == self.terminal and event.type() == event.KeyPress:
            key = event.key()
            text = event.text()
            
            # Handle Enter key
            if key == Qt.Key_Return or key == Qt.Key_Enter:
                if self.ssh_client.is_shell_running():
                    self.ssh_client.send_to_shell(self.command_buffer)
                self.command_buffer = ""
                return True
            
            # Handle Backspace
            elif key == Qt.Key_Backspace:
                if self.command_buffer and self.ssh_client.is_shell_running():
                    self.command_buffer = self.command_buffer[:-1]
                    try:
                        self.ssh_client.shell.send('\b \b')
                    except:
                        pass
                return True
            
            # Handle regular characters
            elif len(text) == 1 and text.isprintable():
                if self.ssh_client.is_shell_running():
                    self.command_buffer += text
                    try:
                        self.ssh_client.shell.send(text)
                    except:
                        pass
                return True
            
            # Handle special keys (arrows, etc.)
            elif key in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                if self.ssh_client.is_shell_running():
                    try:
                        if key == Qt.Key_Up:
                            self.ssh_client.shell.send('\033[A')
                        elif key == Qt.Key_Down:
                            self.ssh_client.shell.send('\033[B')
                        elif key == Qt.Key_Left:
                            self.ssh_client.shell.send('\033[D')
                        elif key == Qt.Key_Right:
                            self.ssh_client.shell.send('\033[C')
                    except:
                        pass
                return True
            
            # Handle Ctrl+C
            elif key == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                if self.ssh_client.is_shell_running():
                    try:
                        self.ssh_client.shell.send('\003')  # Send Ctrl+C
                    except:
                        pass
                    self.command_buffer = ""
                return True
            
            # Handle Ctrl+D (EOF)
            elif key == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
                if self.ssh_client.is_shell_running():
                    try:
                        self.ssh_client.shell.send('\004')  # Send Ctrl+D
                    except:
                        pass
                return True
            
            # Handle Tab for completion
            elif key == Qt.Key_Tab:
                if self.ssh_client.is_shell_running():
                    try:
                        self.ssh_client.shell.send('\t')
                    except:
                        pass
                return True
            
            # Handle Escape
            elif key == Qt.Key_Escape:
                if self.ssh_client.is_shell_running():
                    try:
                        self.ssh_client.shell.send('\033')
                    except:
                        pass
                return True
            
            return True
        
        return super().eventFilter(obj, event)
    
    def closeEvent(self, event):
        """Clean up when widget is closed"""
        if self.ssh_client.is_shell_running():
            self.ssh_client.remove_output_callback(self.append_output)
            self.ssh_client.stop_interactive_shell()
        event.accept()







class MainWindow(QMainWindow):
    """Main application window with tabbed SSH connections"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SSHWOMPER")
        self.resize(900, 700)
        
        self.setWindowIcon(QIcon("nerd.ico"))

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        self.setCentralWidget(self.tabs)

        # Keep track of SSH clients for cleanup
        self.ssh_clients = {}

        self.add_plus_tab()

    def add_plus_tab(self):
        """Add the '+' tab for new connections"""
        login_widget = SSHLoginWidget()
        login_widget.connection_successful.connect(self.create_ssh_widget)
        
        # Remove existing '+' tab if present
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == '+':
                self.tabs.removeTab(i)
                break
        
        # Add new '+' tab
        tab_index = self.tabs.addTab(login_widget, '+')
        self.tabs.setCurrentIndex(tab_index)
        
        # Remove close button from '+' tab
        self.tabs.tabBar().setTabButton(tab_index, QTabBar.RightSide, None)

    def create_ssh_widget(self, ssh_client):
        """Handle successful SSH connection"""
        current_index = self.tabs.currentIndex()
        directory_explorer = DirectoryExplorer(ssh_client)
        
        conn_info = ssh_client.connection_info
        tab_title = f"{conn_info['username']}@{conn_info['hostname']}"
        
        self.tabs.removeTab(current_index)
        new_index = self.tabs.insertTab(current_index, directory_explorer, tab_title)
        self.tabs.setCurrentIndex(new_index)
        
        self.ssh_clients[new_index] = ssh_client
        self.add_plus_tab()

    def disconnect_tab(self, directory_explorer):
        """Handle disconnect request from DirectoryExplorer"""
        # Find the tab containing this directory explorer
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == directory_explorer:
                self.close_tab(i)
                break

    def close_tab(self, index):
        """Close a tab and clean up resources"""
        if self.tabs.tabText(index) != '+':
            # Clean up SSH client if it exists
            if index in self.ssh_clients:
                ssh_client = self.ssh_clients[index]
                ssh_client.disconnect()
                del self.ssh_clients[index]
            
            # Update indices in ssh_clients dict
            updated_clients = {}
            for idx, client in self.ssh_clients.items():
                if idx > index:
                    updated_clients[idx - 1] = client
                elif idx < index:
                    updated_clients[idx] = client
            self.ssh_clients = updated_clients
            self.tabs.removeTab(index)

    def closeEvent(self, event):
        """Clean up all SSH connections when closing the application"""
        for ssh_client in self.ssh_clients.values():
            ssh_client.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    main_window = MainWindow()

    for conn_info in SSHClient.get_saved_clients():
        sshclient = SSHClient.start_saved_client(conn_info)
        main_window.create_ssh_widget(sshclient)

    main_window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
