import sys
import os
from pathlib import Path
import configparser
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTextEdit, QFileDialog, QTabWidget,
    QProgressBar, QMessageBox, QGroupBox, QListWidget, QListWidgetItem,
    QComboBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from pytube import YouTube
import locale

# Application version
VERSION = "25.12.12"


class DownloadThread(QThread):
    """Thread for handling video downloads without blocking the UI"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, download_type, **kwargs):
        super().__init__()
        self.download_type = download_type
        self.kwargs = kwargs
        
    def get_stream(self, yt, stream_type, file_extension, resolution):
        """Get stream based on user preferences"""
        streams = yt.streams
        
        # Apply file extension filter if specified
        if file_extension and file_extension != "auto":
            streams = streams.filter(file_extension=file_extension)
        
        # If audio-only, get best audio
        if stream_type == "audio":
            audio_streams = streams.filter(only_audio=True)
            if audio_streams:
                # Try to get highest quality audio
                return audio_streams.get_audio_only()
            return None
        
        # Apply stream type filter for video streams
        if stream_type == "progressive":
            streams = streams.filter(progressive=True)
        elif stream_type == "adaptive":
            # For adaptive, we need video-only streams (audio would be separate)
            streams = streams.filter(adaptive=True, only_video=True)
        # "auto" - no filter, prefer progressive if available
        
        # For video streams, apply resolution filter if specified
        if resolution and resolution != "auto":
            # Try to get exact resolution
            filtered = streams.filter(res=resolution)
            if filtered:
                return filtered.first()
            # If exact not found, try to get closest lower resolution
            resolution_order = ["1080p", "720p", "480p", "360p", "240p", "144p"]
            if resolution in resolution_order:
                idx = resolution_order.index(resolution)
                for res in resolution_order[idx:]:
                    filtered = streams.filter(res=res)
                    if filtered:
                        return filtered.first()
        
        # Default: get highest resolution available
        if stream_type == "progressive":
            return streams.get_highest_resolution()
        elif stream_type == "adaptive":
            return streams.get_highest_resolution()
        else:
            # Auto/best - prefer progressive if available, otherwise adaptive
            progressive = streams.filter(progressive=True)
            if progressive:
                return progressive.get_highest_resolution()
            # Fallback to adaptive
            adaptive = streams.filter(adaptive=True, only_video=True)
            if adaptive:
                return adaptive.get_highest_resolution()
            # Last resort: any available stream
            return streams.get_highest_resolution()
        
    def run(self):
        try:
            if self.download_type == "single":
                url = self.kwargs.get("url")
                output_path = self.kwargs.get("output_path", ".")
                stream_type = self.kwargs.get("stream_type", "auto")
                file_extension = self.kwargs.get("file_extension", "auto")
                resolution = self.kwargs.get("resolution", "auto")
                
                self.progress.emit("Loading video...")
                
                # Use direct pytube API for more reliable downloads
                yt = YouTube(url)
                self.progress.emit(f"Found video: {yt.title}")
                self.progress.emit("Selecting stream based on preferences...")
                
                # Get stream based on user preferences
                stream = self.get_stream(yt, stream_type, file_extension, resolution)
                if not stream:
                    # Fallback to first available stream
                    stream = yt.streams.first()
                    if not stream:
                        self.finished.emit(False, "No suitable stream found for this video.")
                        return
                
                # Display stream info
                stream_info = []
                if hasattr(stream, 'resolution') and stream.resolution:
                    stream_info.append(f"{stream.resolution}")
                if hasattr(stream, 'abr') and stream.abr:
                    stream_info.append(f"{stream.abr}")
                if hasattr(stream, 'mime_type') and stream.mime_type:
                    stream_info.append(stream.mime_type.split('/')[-1])
                
                info_str = f" ({', '.join(stream_info)})" if stream_info else ""
                
                # Display file size if available
                file_size = ""
                if stream and hasattr(stream, 'filesize_mb') and stream.filesize_mb:
                    file_size = f" ({stream.filesize_mb:.2f} MB)"
                elif stream and hasattr(stream, 'filesize') and stream.filesize:
                    file_size = f" ({stream.filesize / (1024*1024):.2f} MB)"
                
                self.progress.emit(f"Downloading: {yt.title}{info_str}{file_size}")
                stream.download(output_path=output_path)
                
                self.finished.emit(True, f"Download completed: {yt.title}")
                
            elif self.download_type == "list":
                filename = self.kwargs.get("filename")
                output_path = self.kwargs.get("output_path", ".")
                self.progress.emit(f"Reading video list from {filename}...")
                
                # Read URLs from file
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                except Exception as e:
                    self.finished.emit(False, f"Error reading file: {str(e)}")
                    return
                
                if not urls:
                    self.finished.emit(False, "No valid URLs found in the file.")
                    return
                
                self.progress.emit(f"Found {len(urls)} video(s) to download")
                
                # Download each video using direct API
                successful = 0
                failed = 0
                
                stream_type = self.kwargs.get("stream_type", "auto")
                file_extension = self.kwargs.get("file_extension", "auto")
                resolution = self.kwargs.get("resolution", "auto")
                
                for i, url in enumerate(urls, 1):
                    try:
                        self.progress.emit(f"[{i}/{len(urls)}] Loading video: {url}")
                        yt = YouTube(url)
                        self.progress.emit(f"[{i}/{len(urls)}] Found: {yt.title}")
                        
                        # Get stream based on user preferences
                        stream = self.get_stream(yt, stream_type, file_extension, resolution)
                        if not stream:
                            stream = yt.streams.first()
                            if not stream:
                                failed += 1
                                self.progress.emit(f"[{i}/{len(urls)}] ✗ No suitable stream found")
                                continue
                        
                        # Display stream info
                        stream_info = []
                        if hasattr(stream, 'resolution') and stream.resolution:
                            stream_info.append(f"{stream.resolution}")
                        if hasattr(stream, 'abr') and stream.abr:
                            stream_info.append(f"{stream.abr}")
                        if hasattr(stream, 'mime_type') and stream.mime_type:
                            stream_info.append(stream.mime_type.split('/')[-1])
                        
                        info_str = f" ({', '.join(stream_info)})" if stream_info else ""
                        
                        # Display file size if available
                        file_size = ""
                        if stream and hasattr(stream, 'filesize_mb') and stream.filesize_mb:
                            file_size = f" ({stream.filesize_mb:.2f} MB)"
                        elif stream and hasattr(stream, 'filesize') and stream.filesize:
                            file_size = f" ({stream.filesize / (1024*1024):.2f} MB)"
                        
                        self.progress.emit(f"[{i}/{len(urls)}] Downloading: {yt.title}{info_str}{file_size}")
                        stream.download(output_path=output_path)
                        successful += 1
                        self.progress.emit(f"[{i}/{len(urls)}] ✓ Completed: {yt.title}")
                    except Exception as e:
                        failed += 1
                        self.progress.emit(f"[{i}/{len(urls)}] ✗ Failed: {str(e)}")
                
                result_msg = f"Downloaded {successful} video(s) successfully"
                if failed > 0:
                    result_msg += f", {failed} failed"
                self.finished.emit(True, result_msg)
                
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class YouTubeDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.download_thread = None
        self.config_file = Path(__file__).parent / "config.ini"
        self.config_data = self.load_config()
        self.output_directory = self.config_data.get('output_directory', str(Path.home() / "Downloads"))
        self.stream_type_index = self.config_data.get('stream_type_index', 0)
        self.file_extension_index = self.config_data.get('file_extension_index', 0)
        self.resolution_index = self.config_data.get('resolution_index', 0)
        self.init_ui()
        
    def load_config(self):
        """Load configuration from config.ini file"""
        config = configparser.ConfigParser()
        default_directory = str(Path.home() / "Downloads")
        
        settings = {
            'output_directory': default_directory,
            'stream_type_index': 0,
            'file_extension_index': 0,
            'resolution_index': 0
        }
        
        if self.config_file.exists():
            try:
                config.read(self.config_file)
                if config.has_section('Settings'):
                    # Load output directory
                    if config.has_option('Settings', 'output_directory'):
                        saved_directory = config.get('Settings', 'output_directory')
                        if os.path.exists(saved_directory) and os.path.isdir(saved_directory):
                            settings['output_directory'] = saved_directory
                    
                    # Load stream type index
                    if config.has_option('Settings', 'stream_type_index'):
                        try:
                            settings['stream_type_index'] = config.getint('Settings', 'stream_type_index')
                        except (ValueError, configparser.NoOptionError):
                            pass
                    
                    # Load file extension index
                    if config.has_option('Settings', 'file_extension_index'):
                        try:
                            settings['file_extension_index'] = config.getint('Settings', 'file_extension_index')
                        except (ValueError, configparser.NoOptionError):
                            pass
                    
                    # Load resolution index
                    if config.has_option('Settings', 'resolution_index'):
                        try:
                            settings['resolution_index'] = config.getint('Settings', 'resolution_index')
                        except (ValueError, configparser.NoOptionError):
                            pass
            except Exception as e:
                # If there's an error reading config, use defaults
                print(f"Error reading config: {e}")
        
        return settings
    
    def save_config(self):
        """Save configuration to config.ini file"""
        config = configparser.ConfigParser()
        
        # Read existing config if it exists
        if self.config_file.exists():
            config.read(self.config_file)
        
        # Create Settings section if it doesn't exist
        if not config.has_section('Settings'):
            config.add_section('Settings')
        
        # Save output directory
        config.set('Settings', 'output_directory', self.output_directory)
        
        # Save format settings (from single video tab, which is the default)
        if hasattr(self, 'stream_type_combo'):
            config.set('Settings', 'stream_type_index', str(self.stream_type_combo.currentIndex()))
            config.set('Settings', 'file_extension_index', str(self.file_extension_combo.currentIndex()))
            config.set('Settings', 'resolution_index', str(self.resolution_combo.currentIndex()))
        
        # Write to file
        try:
            with open(self.config_file, 'w') as configfile:
                config.write(configfile)
        except Exception as e:
            print(f"Error saving config: {e}")
        
    def init_ui(self):
        self.setWindowTitle(f"pyTuber v{VERSION}")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel(f"pyTuber v{VERSION}")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Output directory selection
        dir_group = QGroupBox("Output Directory")
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel(self.output_directory)
        self.dir_label.setStyleSheet("padding: 5px; background-color: #f0f0f0; border: 1px solid #ccc;")
        dir_button = QPushButton("Browse...")
        dir_button.clicked.connect(self.select_output_directory)
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(dir_button)
        dir_group.setLayout(dir_layout)
        main_layout.addWidget(dir_group)
        
        # Tab widget for different download types
        self.tabs = QTabWidget()
        
        # Single video download tab
        self.single_tab = self.create_single_video_tab()
        self.tabs.addTab(self.single_tab, "Single Video")
        
        # List download tab
        self.list_tab = self.create_list_tab()
        self.tabs.addTab(self.list_tab, "Video List")
        
        main_layout.addWidget(self.tabs)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # Status log
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout()
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumHeight(150)
        self.status_log.setStyleSheet("background-color: #f9f9f9; font-family: monospace;")
        log_layout.addWidget(self.status_log)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # Add initial status message
        self.log_message("Application started. Ready to download videos.")
        
    def create_format_options_group(self, stream_type_idx=0, file_ext_idx=0, resolution_idx=0, is_list_tab=False):
        """Create format options group box"""
        group = QGroupBox("Download Format Options")
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Stream type selection
        stream_type_layout = QHBoxLayout()
        stream_type_label = QLabel("Stream Type:")
        stream_type_label.setMinimumWidth(100)
        stream_type_layout.addWidget(stream_type_label)
        
        stream_type_combo = QComboBox()
        stream_type_combo.addItems(["Auto (Best Available)", "Progressive (Video+Audio)", "Adaptive (DASH)", "Audio Only"])
        stream_type_combo.setCurrentIndex(stream_type_idx)
        stream_type_combo.currentIndexChanged.connect(self.save_config)
        stream_type_layout.addWidget(stream_type_combo)
        layout.addLayout(stream_type_layout)
        
        # File extension selection
        file_ext_layout = QHBoxLayout()
        file_ext_label = QLabel("File Format:")
        file_ext_label.setMinimumWidth(100)
        file_ext_layout.addWidget(file_ext_label)
        
        file_extension_combo = QComboBox()
        file_extension_combo.addItems(["Auto", "mp4", "webm"])
        file_extension_combo.setCurrentIndex(file_ext_idx)
        file_extension_combo.currentIndexChanged.connect(self.save_config)
        file_ext_layout.addWidget(file_extension_combo)
        layout.addLayout(file_ext_layout)
        
        # Resolution selection (for video streams)
        resolution_layout = QHBoxLayout()
        resolution_label = QLabel("Resolution:")
        resolution_label.setMinimumWidth(100)
        resolution_layout.addWidget(resolution_label)
        
        resolution_combo = QComboBox()
        resolution_combo.addItems(["Auto (Highest)", "1080p", "720p", "480p", "360p", "240p", "144p"])
        resolution_combo.setCurrentIndex(resolution_idx)
        resolution_combo.currentIndexChanged.connect(self.save_config)
        resolution_layout.addWidget(resolution_combo)
        layout.addLayout(resolution_layout)
        
        # Store references for single video tab
        if not is_list_tab:
            self.stream_type_combo = stream_type_combo
            self.file_extension_combo = file_extension_combo
            self.resolution_combo = resolution_combo
        
        group.setLayout(layout)
        return group
        
    def create_single_video_tab(self):
        """Create the single video download tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # URL input
        url_label = QLabel("YouTube Video URL:")
        url_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(url_label)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.setStyleSheet("padding: 8px; font-size: 11px;")
        layout.addWidget(self.url_input)
        
        # Format options (use saved settings)
        format_group = self.create_format_options_group(
            self.stream_type_index,
            self.file_extension_index,
            self.resolution_index,
            is_list_tab=False
        )
        layout.addWidget(format_group)
        
        # Download button
        download_button = QPushButton("Download Video")
        download_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        download_button.clicked.connect(self.download_single_video)
        layout.addWidget(download_button)
        
        layout.addStretch()
        return widget
        
    def create_list_tab(self):
        """Create the video list download tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # File selection
        file_label = QLabel("Select video list file (one URL per line):")
        file_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(file_label)
        
        file_layout = QHBoxLayout()
        self.list_file_label = QLabel("No file selected")
        self.list_file_label.setStyleSheet("padding: 5px; background-color: #f0f0f0; border: 1px solid #ccc;")
        file_button = QPushButton("Select File...")
        file_button.clicked.connect(self.select_list_file)
        file_layout.addWidget(self.list_file_label)
        file_layout.addWidget(file_button)
        layout.addLayout(file_layout)
        
        # Format options (create separate instance for list tab, use saved settings)
        self.list_format_group = self.create_format_options_group(
            self.stream_type_index,
            self.file_extension_index,
            self.resolution_index,
            is_list_tab=True
        )
        layout.addWidget(self.list_format_group)
        
        # Download button
        download_button = QPushButton("Download from List")
        download_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        download_button.clicked.connect(self.download_from_list)
        layout.addWidget(download_button)
        
        layout.addStretch()
        return widget
        
    def select_output_directory(self):
        """Open dialog to select output directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self.output_directory
        )
        if directory:
            self.output_directory = directory
            self.dir_label.setText(directory)
            self.save_config()  # Save the new directory to config
            self.log_message(f"Output directory set to: {directory}")
            
    def select_list_file(self):
        """Open dialog to select video list file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video List File",
            "",
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            self.list_file_path = filename
            self.list_file_label.setText(os.path.basename(filename))
            self.log_message(f"Selected list file: {filename}")
            
    def get_format_options(self, format_group=None):
        """Get format options from UI"""
        if format_group is None:
            # Use single video tab format options
            stream_type_idx = self.stream_type_combo.currentIndex()
            file_ext_idx = self.file_extension_combo.currentIndex()
            resolution_idx = self.resolution_combo.currentIndex()
        else:
            # Use list tab format options
            children = format_group.findChildren(QComboBox)
            stream_type_idx = children[0].currentIndex() if len(children) > 0 else 0
            file_ext_idx = children[1].currentIndex() if len(children) > 1 else 0
            resolution_idx = children[2].currentIndex() if len(children) > 2 else 0
        
        # Map stream type
        stream_type_map = {
            0: "auto",
            1: "progressive",
            2: "adaptive",
            3: "audio"
        }
        stream_type = stream_type_map.get(stream_type_idx, "auto")
        
        # Map file extension
        file_ext_map = {
            0: "auto",
            1: "mp4",
            2: "webm"
        }
        file_extension = file_ext_map.get(file_ext_idx, "auto")
        
        # Map resolution
        resolution_map = {
            0: "auto",
            1: "1080p",
            2: "720p",
            3: "480p",
            4: "360p",
            5: "240p",
            6: "144p"
        }
        resolution = resolution_map.get(resolution_idx, "auto")
        
        return stream_type, file_extension, resolution
            
    def download_single_video(self):
        """Download a single video"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a YouTube video URL.")
            return
            
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, "Warning", "A download is already in progress.")
            return
            
        # Get format options
        stream_type, file_extension, resolution = self.get_format_options()
        
        self.log_message(f"Starting download: {url}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Store original directory but pass output path to thread
        original_dir = os.getcwd()
        
        self.download_thread = DownloadThread(
            "single", 
            url=url, 
            output_path=self.output_directory,
            stream_type=stream_type,
            file_extension=file_extension,
            resolution=resolution
        )
        self.download_thread.progress.connect(self.on_progress)
        self.download_thread.finished.connect(lambda success, msg: self.on_download_finished(success, msg, original_dir))
        self.download_thread.start()
        
    def download_from_list(self):
        """Download videos from a list file"""
        if not hasattr(self, 'list_file_path') or not self.list_file_path:
            QMessageBox.warning(self, "Warning", "Please select a video list file.")
            return
            
        if not os.path.exists(self.list_file_path):
            QMessageBox.warning(self, "Warning", "The selected file does not exist.")
            return
            
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, "Warning", "A download is already in progress.")
            return
            
        # Get format options from list tab
        stream_type, file_extension, resolution = self.get_format_options(self.list_format_group)
        
        self.log_message(f"Starting download from list: {self.list_file_path}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        original_dir = os.getcwd()
        
        self.download_thread = DownloadThread(
            "list", 
            filename=self.list_file_path, 
            output_path=self.output_directory,
            stream_type=stream_type,
            file_extension=file_extension,
            resolution=resolution
        )
        self.download_thread.progress.connect(self.on_progress)
        self.download_thread.finished.connect(lambda success, msg: self.on_download_finished(success, msg, original_dir))
        self.download_thread.start()
        
    def on_progress(self, message):
        """Handle progress updates"""
        self.log_message(message)
        
    def on_download_finished(self, success, message, original_dir):
        """Handle download completion"""
        self.progress_bar.setVisible(False)
        self.log_message(message)
        
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)
            
    def log_message(self, message):
        """Add a message to the status log"""
        self.status_log.append(f"[{self.get_timestamp()}] {message}")
        # Auto-scroll to bottom
        self.status_log.verticalScrollBar().setValue(
            self.status_log.verticalScrollBar().maximum()
        )
        
    def get_timestamp(self):
        """Get current timestamp string"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
        
    def closeEvent(self, event):
        """Handle window close event"""
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Download in Progress",
                "A download is currently in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.download_thread.terminate()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    # Set locale to avoid 'en-US' errors
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'en-US')
        except locale.Error:
            # If locale setting fails, continue anyway
            pass
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Modern look
    
    window = YouTubeDownloaderGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

