
import sys
import os
import stat
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QListWidgetItem, QPushButton, QLabel,
                             QMessageBox, QLineEdit, QDialog, QFormLayout,
                             QDialogButtonBox, QTextEdit, QSplitter, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import paramiko
from datetime import datetime

class SSHLoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.ssh_client = None
        self.sftp_client = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle('SSH Login')
        self.setFixedSize(450, 250)
        
        layout = QVBoxLayout()
        
        # Form layout for inputs
        form_layout = QFormLayout()
        
        # Hostname input
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText('hostname or IP address')
        form_layout.addRow('Hostname:', self.hostname_input)
        
        # Username input
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('username')
        form_layout.addRow('Username:', self.username_input)
        
        # Password input
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText('Leave empty for key-based auth')
        form_layout.addRow('Password (optional):', self.password_input)
        
        # Port input
        self.port_input = QLineEdit()
        self.port_input.setText('22')
        self.port_input.setPlaceholderText('22')
        form_layout.addRow('Port:', self.port_input)
        
        layout.addLayout(form_layout)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Info label
        info_label = QLabel('Note: For key-based authentication, ensure your SSH keys are in ~/.ssh/')
        info_label.setWordWrap(True)
        info_label.setStyleSheet('color: gray; font-size: 10px;')
        layout.addWidget(info_label)
        
        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.test_connection)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
        self.setLayout(layout)
    
    def test_connection(self):
        """Test SSH connection using paramiko"""
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        port = int(self.port_input.text().strip() or '22')
        
        if not hostname or not username:
            QMessageBox.warning(self, 'Error', 'Please enter both hostname and username')
            return
        
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.button_box.setEnabled(False)
        QApplication.processEvents()
        
        try:
            # Create SSH client
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
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
                # Try key-based authentication
                self.ssh_client.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    timeout=10
                )
            
            # Test connection with a simple command
            stdin, stdout, stderr = self.ssh_client.exec_command('whoami')
            result = stdout.read().decode().strip()
            
            if result == username:
                # Create SFTP client
                self.sftp_client = self.ssh_client.open_sftp()
                self.accept()
            else:
                raise Exception("Authentication verification failed")
                
        except paramiko.AuthenticationException:
            QMessageBox.critical(self, 'Authentication Failed', 'Invalid username or password.')
            self.cleanup_connection()
        except paramiko.SSHException as e:
            QMessageBox.critical(self, 'SSH Error', f'SSH connection failed:\n{str(e)}')
            self.cleanup_connection()
        except Exception as e:
            QMessageBox.critical(self, 'Connection Failed', f'Failed to connect:\n{str(e)}')
            self.cleanup_connection()
        finally:
            # Hide progress
            self.progress_bar.setVisible(False)
            self.button_box.setEnabled(True)
    
    def cleanup_connection(self):
        """Clean up failed connection attempts"""
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

class DirectoryExplorer(QWidget):
    def __init__(self, ssh_client, sftp_client, connection_info):
        super().__init__()
        self.ssh_client = ssh_client
        self.sftp_client = sftp_client
        self.connection_info = connection_info
        self.current_path = self.sftp_client.getcwd() or '/'
        self.init_ui()
        self.go_home()  # Start at home directory
    
    def init_ui(self):
        # Set window properties
        self.setWindowTitle(f'SSH Directory Explorer - {self.connection_info["username"]}@{self.connection_info["hostname"]}')
        self.setGeometry(200, 200, 900, 700)
        
        # Main layout
        main_layout = QVBoxLayout()

        # Top status layout (connection + path)
        status_layout = QHBoxLayout()

        # Top bar: connection info + path in a single row
        top_bar = QHBoxLayout()

        connection_text = f'Connected to: {self.connection_info["username"]}@{self.connection_info["hostname"]}:{self.connection_info["port"]}'
        connection_label = QLabel(connection_text)
        connection_label.setStyleSheet('color: #2e7d32; font-weight: bold; font-size: 11px;')

        self.path_label = QLabel(f"Current Path: {self.current_path}")
        self.path_label.setStyleSheet("font-size: 11px; color: #555; padding-left: 15px;")

        top_bar.addWidget(connection_label)
        top_bar.addWidget(self.path_label)
        top_bar.addStretch()  # Push everything to the left

        main_layout.addLayout(top_bar)

        status_layout.addWidget(connection_label)
        status_layout.addSpacing(20)
        status_layout.addWidget(self.path_label)
        status_layout.addStretch()
        
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
        
        # Command output area
        output_widget = QWidget()
        output_layout = QVBoxLayout()
        output_layout.addWidget(QLabel('Activity Log:'))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(150)
        self.output_text.setFont(QFont('Courier', 9))
        output_layout.addWidget(self.output_text)
        output_widget.setLayout(output_layout)
        splitter.addWidget(output_widget)
        
        splitter.setSizes([700, 200])
        
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
        main_layout.addLayout(status_layout)
        main_layout.addLayout(nav_layout)
        main_layout.addWidget(splitter)
        main_layout.addLayout(input_layout)
        
        self.setLayout(main_layout)
        
        # Log initial connection
        self.log_activity(f"Connected to {connection_text}")
    
    def log_activity(self, message):
        """Log activity to the output area"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_text.append(f"[{timestamp}] {message}")
        
        # Auto-scroll to bottom
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def execute_command(self, command):
        """Execute a command via SSH and return the output"""
        try:
            self.log_activity(f"Executing: {command}")
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            
            stdout_data = stdout.read().decode().strip()
            stderr_data = stderr.read().decode().strip()
            return_code = stdout.channel.recv_exit_status()
            
            if stdout_data:
                self.log_activity(f"Output: {stdout_data[:100]}{'...' if len(stdout_data) > 100 else ''}")
            if stderr_data:
                self.log_activity(f"Error: {stderr_data}")
            
            return stdout_data, stderr_data, return_code
            
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            self.log_activity(error_msg)
            return "", error_msg, 1
    
    def refresh_directory(self):
        """Refresh the directory listing using SFTP"""
        try:
            self.dir_list.clear()
            self.log_activity(f"Listing directory: {self.current_path}")
            
            # Update path label
            self.path_label.setText(f"Current Path: {self.current_path}")
            
            # Get directory listing
            file_list = self.sftp_client.listdir_attr(self.current_path)
            
            # Add parent directory if not at root
            if self.current_path != '/':
                parent_item = QListWidgetItem("📁 .. (Parent Directory)")
                parent_item.setData(Qt.UserRole, ('dir', '..'))
                self.dir_list.addItem(parent_item)
            
            # Sort: directories first, then files
            directories = []
            files = []
            
            for file_attr in file_list:
                name = file_attr.filename
                if name in ['.', '..']:
                    continue
                
                # Determine file type
                if stat.S_ISDIR(file_attr.st_mode):
                    directories.append((name, file_attr))
                elif stat.S_ISLNK(file_attr.st_mode):
                    files.append((name, file_attr, 'link'))
                elif stat.S_ISREG(file_attr.st_mode):
                    # Check if executable
                    if file_attr.st_mode & stat.S_IXUSR:
                        files.append((name, file_attr, 'executable'))
                    else:
                        files.append((name, file_attr, 'file'))
                else:
                    files.append((name, file_attr, 'other'))
            
            # Add directories
            for name, file_attr in sorted(directories):
                item = QListWidgetItem(f"📁 {name}")
                item.setData(Qt.UserRole, ('dir', name))
                self.dir_list.addItem(item)
            
            # Add files
            for name, file_attr, file_type in sorted(files):
                if file_type == 'link':
                    icon = "🔗"
                elif file_type == 'executable':
                    icon = "⚙️"
                elif file_type == 'other':
                    icon = "❓"
                else:
                    icon = "📄"
                
                # Add size info for files
                if stat.S_ISREG(file_attr.st_mode):
                    size = self.format_file_size(file_attr.st_size)
                    item_text = f"{icon} {name} ({size})"
                else:
                    item_text = f"{icon} {name}"
                
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, (file_type, name))
                self.dir_list.addItem(item)
            
            self.log_activity(f"Listed {len(file_list)} items")
            
        except Exception as e:
            error_msg = f"Failed to list directory: {str(e)}"
            self.log_activity(error_msg)
            QMessageBox.warning(self, "Error", error_msg)
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f}{size_names[i]}"
    
    def item_double_clicked(self, item):
        """Handle double-click on directory items"""
        item_type, name = item.data(Qt.UserRole)
        
        if item_type == 'dir' or item_type == 'link':
            self.navigate_to_directory(name)
    
    def navigate_to_directory(self, dir_name):
        """Navigate to a directory using SFTP"""
        try:
            if dir_name == '..':
                # Go to parent directory
                new_path = os.path.dirname(self.current_path.rstrip('/'))
                if not new_path:
                    new_path = '/'
            elif dir_name.startswith('/'):
                # Absolute path
                new_path = dir_name
            else:
                # Relative path
                new_path = os.path.join(self.current_path, dir_name)
            
            # Normalize path
            new_path = os.path.normpath(new_path).replace('\\', '/')
            if not new_path.startswith('/'):
                new_path = '/' + new_path
            
            # Test if directory exists and is accessible
            self.sftp_client.chdir(new_path)
            self.current_path = self.sftp_client.getcwd()
            self.refresh_directory()
            
        except Exception as e:
            error_msg = f"Cannot access directory '{dir_name}': {str(e)}"
            self.log_activity(error_msg)
            QMessageBox.warning(self, "Navigation Error", error_msg)
    
    def go_back(self):
        """Go to parent directory"""
        if self.current_path != '/':
            self.navigate_to_directory('..')
    
    def go_home(self):
        """Go to user home directory"""
        try:
            # Get home directory
            stdout, stderr, returncode = self.execute_command('echo $HOME')
            if returncode == 0 and stdout:
                home_path = stdout.strip()
                self.sftp_client.chdir(home_path)
                self.current_path = self.sftp_client.getcwd()
                self.refresh_directory()
            else:
                # Fallback: try to cd to ~
                self.sftp_client.chdir('.')
                self.current_path = self.sftp_client.getcwd()
                self.refresh_directory()
        except Exception as e:
            self.log_activity(f"Could not navigate to home: {str(e)}")
            self.refresh_directory()
    
    def go_root(self):
        """Go to root directory"""
        try:
            self.sftp_client.chdir('/')
            self.current_path = self.sftp_client.getcwd()
            self.refresh_directory()
        except Exception as e:
            error_msg = f"Cannot access root directory: {str(e)}"
            self.log_activity(error_msg)
            QMessageBox.warning(self, "Navigation Error", error_msg)
    
    def navigate_to_path(self):
        """Navigate to manually entered path"""
        path = self.path_input.text().strip()
        if not path:
            return
        
        # Expand ~ to home directory if needed
        if path.startswith('~'):
            stdout, stderr, returncode = self.execute_command(f'echo {path}')
            if returncode == 0 and stdout:
                path = stdout.strip()
        
        try:
            self.sftp_client.chdir(path)
            self.current_path = self.sftp_client.getcwd()
            self.path_input.clear()
            self.refresh_directory()
        except Exception as e:
            error_msg = f"Cannot access path '{path}': {str(e)}"
            self.log_activity(error_msg)
            QMessageBox.warning(self, "Path Error", error_msg)
    
    def disconnect(self):
        """Disconnect and return to login screen"""
        reply = QMessageBox.question(self, 'Disconnect', 'Are you sure you want to disconnect?')
        if reply == QMessageBox.Yes:
            self.log_activity("Disconnecting...")
            try:
                if self.sftp_client:
                    self.sftp_client.close()
                if self.ssh_client:
                    self.ssh_client.close()
            except:
                pass
            self.close()
    
    def closeEvent(self, event):
        """Handle window close event"""
        try:
            if self.sftp_client:
                self.sftp_client.close()
            if self.ssh_client:
                self.ssh_client.close()
        except:
            pass
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    login_dialog = SSHLoginDialog()
    if login_dialog.exec_() == QDialog.Accepted:
        # Create connection info
        connection_info = {
            'hostname': login_dialog.hostname_input.text().strip(),
            'username': login_dialog.username_input.text().strip(),
            'port': int(login_dialog.port_input.text().strip() or '22')
        }
        
        # Create and show directory explorer
        explorer = DirectoryExplorer(
            login_dialog.ssh_client,
            login_dialog.sftp_client,
            connection_info
        )
        explorer.show()
        sys.exit(app.exec_())
    else:
        sys.exit(0)



if __name__ == '__main__':
    main()

