import sys
import os
import stat
import appdirs
import collections

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QListWidgetItem, QPushButton, QLabel,
                             QMessageBox, QLineEdit, QFormLayout,
                             QTextEdit, QSplitter, QProgressBar, QTabWidget,
                             QMainWindow, QTabBar, QStackedWidget)

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
import paramiko
from datetime import datetime




class SSHClient:
    """Handles SSH connection and remote operations"""
    
    def __init__(self):
        self.ssh_client = None
        self.sftp_client = None
        self.current_path = None
        self.history = collections.deque(maxlen=200)
        self.connection_info = {}
    
    def connect(self, hostname, username, password=None, port=22):
        """Establish SSH connection"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Store connection info
            self.connection_info = {
                'hostname': hostname,
                'username': username,
                'port': port
            }
            
            # Connect with password or key-based auth
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
            
            return True
            
        except Exception as e:
            self.disconnect()
            raise e
    
    def disconnect(self):
        """Close SSH and SFTP connections"""
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

            command_ = parts[10]
            if command_ == command:
                continue # dont display usage of ps aux
            
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





class SSHWidget(QWidget):
    def __init__(self, ssh_client):
        super().__init__()
        self.ssh_client = ssh_client
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.nav_bar = QListWidget()
        self.nav_bar.setObjectName("navBar")
        self.nav_bar.setFixedWidth(150)
        self.nav_bar.setMovement(QListWidget.Static)
        self.nav_bar.setSpacing(2)

        nav_items = ["Files", "Processes"]
        for text in nav_items:
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self.nav_bar.addItem(item)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("contentArea")

        self.directory_widget = self.create_explorer_with_terminal(DirectoryExplorer(self.ssh_client))
        self.processes_widget = self.create_explorer_with_terminal(ProcessExplorer(self.ssh_client))

        self.stacked_widget.addWidget(self.directory_widget)
        self.stacked_widget.addWidget(self.processes_widget)

        main_layout.addWidget(self.nav_bar)
        main_layout.addWidget(self.stacked_widget, 1)

        self.nav_bar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        self.apply_stylesheet()

        if self.nav_bar.count() > 0:
            self.nav_bar.setCurrentRow(0)

    def create_explorer_with_terminal(self, explorer_widget):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        from PyQt5.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Vertical)
        
        splitter.addWidget(explorer_widget)
        
        terminal_widget = CommandLineWidget(self.ssh_client)
        splitter.addWidget(terminal_widget)
        
        splitter.setSizes([600, 200])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, True)
        
        layout.addWidget(splitter)
        return container

    def apply_stylesheet(self):
        style = """
            QListWidget#navBar {
                background-color: #2d2d2d;
                border: 1px solid #444444;
                outline: 0;
            }

            QListWidget#navBar::item {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 12px 8px;
                margin: 2px 4px;
                border: 1px solid #555555;
                border-radius: 5px;
            }

            QListWidget#navBar::item:hover {
                background-color: #4d4d4d;
                border: 1px solid #666666;
            }

            QListWidget#navBar::item:selected {
                background-color: #0078d4;
                color: white;
                border: 1px solid #005a9e;
            }

            QStackedWidget#contentArea {
                background-color: #ffffff;
                border: 1px solid #cccccc;
            }
        """
        self.setStyleSheet(style)

    def disconnect_tab(self, widget):
        if hasattr(self, 'parent_window'):
            self.parent_window.disconnect_tab(self)
        else:
            self.ssh_client.disconnect()
            self.close()


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

        main_layout.addLayout(top_bar)
        
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
        main_layout.addLayout(nav_layout)
        main_layout.addWidget(splitter)
        main_layout.addLayout(input_layout)
        
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




class CommandLineWidget(QWidget):
    def __init__(self, ssh_client):
        super().__init__()
        self.ssh_client = ssh_client
        self.command_history = []
        self.history_index = -1
        self.init_ui()
        self.update_display()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont('Courier', 10))
        self.output_text.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        layout.addWidget(self.output_text)
        
        input_layout = QHBoxLayout()
        
        conn_info = self.ssh_client.connection_info
        prompt_text = f"{conn_info['username']}@{conn_info['hostname']}:$ "
        self.prompt_label = QLabel(prompt_text)
        self.prompt_label.setFont(QFont('Courier', 10))
        self.prompt_label.setStyleSheet("color: #00ff00; background-color: #1e1e1e; padding: 5px;")
        
        self.command_input = QLineEdit()
        self.command_input.setFont(QFont('Courier', 10))
        self.command_input.setStyleSheet("background-color: #1e1e1e; color: #ffffff; border: 1px solid #444; padding: 5px;")
        self.command_input.returnPressed.connect(self.execute_command)
        
        input_layout.addWidget(self.prompt_label)
        input_layout.addWidget(self.command_input)
        
        layout.addLayout(input_layout)
        self.setLayout(layout)
        
        self.command_input.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        if obj == self.command_input and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Up:
                self.navigate_history(-1)
                return True
            elif event.key() == Qt.Key_Down:
                self.navigate_history(1)
                return True
        return super().eventFilter(obj, event)
    
    def navigate_history(self, direction):
        if not self.command_history:
            return
        
        self.history_index += direction
        
        if self.history_index < 0:
            self.history_index = 0
        elif self.history_index >= len(self.command_history):
            self.history_index = len(self.command_history) - 1
        
        if 0 <= self.history_index < len(self.command_history):
            self.command_input.setText(self.command_history[self.history_index])
    
    def execute_command(self):
        command = self.command_input.text().strip()
        if not command:
            return
        
        self.command_history.append(command)
        self.history_index = len(self.command_history)
        
        conn_info = self.ssh_client.connection_info
        current_path = self.ssh_client.get_current_path()
        prompt = f"{conn_info['username']}@{conn_info['hostname']}:{current_path}$ {command}"
        
        self.output_text.append(prompt)
        self.command_input.clear()
        
        try:
            self.ssh_client.execute_user_command(command)
            self.update_display()
        except Exception as e:
            self.output_text.append(f"Error: {str(e)}")
        
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def update_display(self):
        history = self.ssh_client.get_user_command_history()
        
        self.output_text.clear()
        
        for entry in history:
            self.output_text.append(entry)
        
        conn_info = self.ssh_client.connection_info
        current_path = self.ssh_client.get_current_path()
        prompt_text = f"{conn_info['username']}@{conn_info['hostname']}:{current_path}$ "
        self.prompt_label.setText(prompt_text)




def get_settings():
    pass

def save_settings():
    pass



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
        login_widget.connection_successful.connect(self.on_connection_successful)
        
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

    def on_connection_successful(self, ssh_client):
        """Handle successful SSH connection"""
        current_index = self.tabs.currentIndex()
        directory_explorer = SSHWidget(ssh_client)
        
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
    main_window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
