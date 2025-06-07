#!/usr/bin/env python3
import sys
import threading
import time
import os

from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QTextCursor

import paramiko

from dotenv import load_dotenv

load_dotenv()


class SSHShell(QThread):
    output_received = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.shell = None
        self.connected = False
        
        # Hardcoded connection details
        self.hostname = os.getenv("HOST")
        self.username = os.getenv("USER")
        self.password = None
        
    def connect_ssh(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.hostname, username=self.username, password=self.password)
            
            self.shell = self.client.invoke_shell()
            self.shell.settimeout(0.1)
            self.connected = True
            
            self.output_received.emit(f"Connected to {self.hostname}\n")
            return True
        except Exception as e:
            self.output_received.emit(f"Connection failed: {str(e)}\n")
            return False
    
    def send_command(self, command):
        if self.shell and self.connected:
            self.shell.send(command + '\n')
    
    def run(self):
        if not self.connect_ssh():
            return
            
        while self.connected:
            try:
                if self.shell.recv_ready():
                    output = self.shell.recv(1024).decode('utf-8', errors='ignore')
                    # Filter out common ANSI escape sequences
                    output = self.filter_ansi(output)
                    self.output_received.emit(output)
                time.sleep(0.1)
            except Exception as e:
                if "timed out" not in str(e).lower():
                    self.output_received.emit(f"Error: {str(e)}\n")
                    break
    
    def filter_ansi(self, text):
        import re
        # Remove ANSI escape sequences more comprehensively
        ansi_escape = re.compile(r'\x1b(?:\[[?0-9;]*[a-zA-Z]|\][0-9];.*?\x07|[()][AB012])')
        return ansi_escape.sub('', text)

    
    def disconnect(self):
        self.connected = False
        if self.shell:
            self.shell.close()
        if self.client:
            self.client.close()

class SSHTerminal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.ssh_shell = SSHShell()
        self.ssh_shell.output_received.connect(self.append_output)
        self.ssh_shell.start()
        
        self.command_buffer = ""
        
    def init_ui(self):
        self.setWindowTitle("Simple SSH Shell")
        self.setGeometry(100, 100, 800, 600)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create terminal text area
        self.terminal = QTextEdit()
        self.terminal.setFont(QFont("Courier", 10))
        self.terminal.setStyleSheet("""
            QTextEdit {
                background-color: black;
                color: white;
                border: none;
            }
        """)
        
        layout.addWidget(self.terminal)
        
        # Set focus to terminal
        self.terminal.setFocus()
        
        # Install event filter to capture key presses
        self.terminal.installEventFilter(self)
    
    def append_output(self, text):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.terminal.setTextCursor(cursor)
        self.terminal.ensureCursorVisible()
    
    def eventFilter(self, obj, event):
        if obj == self.terminal and event.type() == event.KeyPress:
            key = event.key()
            text = event.text()
            
            # Handle Enter key
            if key == Qt.Key_Return or key == Qt.Key_Enter:
                self.ssh_shell.send_command(self.command_buffer)
                self.command_buffer = ""
                return True
            
            # Handle Backspace
            elif key == Qt.Key_Backspace:
                if self.command_buffer:
                    self.command_buffer = self.command_buffer[:-1]
                    # Remove last character from display
                    cursor = self.terminal.textCursor()
                    cursor.deletePreviousChar()
                return True
            
            # Handle regular characters
            elif len(text) == 1 and text.isprintable():
                self.command_buffer += text
                cursor = self.terminal.textCursor()
                cursor.insertText(text)
                return True
            
            # Handle special keys (arrows, etc.)
            elif key in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                # For vi and other applications, send these directly
                if key == Qt.Key_Up:
                    self.ssh_shell.send_command('\033[A')
                elif key == Qt.Key_Down:
                    self.ssh_shell.send_command('\033[B')
                elif key == Qt.Key_Left:
                    self.ssh_shell.send_command('\033[D')
                elif key == Qt.Key_Right:
                    self.ssh_shell.send_command('\033[C')
                return True
            
            # Handle Ctrl+C
            elif key == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                self.ssh_shell.send_command('\003')  # Send Ctrl+C
                self.command_buffer = ""
                return True
            
            return True
        
        return super().eventFilter(obj, event)
    
    def closeEvent(self, event):
        self.ssh_shell.disconnect()
        self.ssh_shell.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    terminal = SSHTerminal()
    terminal.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()



