



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




