import os, sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QSlider, QVBoxLayout, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rotating Image with Speed Slider")

        # Create central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)

        # Canvas for drawing
        self.view = QGraphicsView(self)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 1280, 720)
        self.view.setScene(self.scene)
        self.view.setFixedSize(1280, 720)
        layout.addWidget(self.view)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # QSlider to control rotation speed
        layout.addWidget(QLabel("Rotation Speed"))
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(5)
        layout.addWidget(self.slider)

        # QSlider to control zoom
        layout.addWidget(QLabel("Zoom"))
        self.zoom_slider = QSlider(Qt.Horizontal, self)
        self.zoom_slider.setRange(1, 1000)
        self.zoom_slider.setValue(100)
        layout.addWidget(self.zoom_slider)

        # Load the placeholder image
        self.placeholder_image = QPixmap("./assets/sol_placeholder.png")
        self.angle = 0
        self.pixmap_item = QGraphicsPixmapItem(self.placeholder_image)
        self.scene.addItem(self.pixmap_item)
        self.pixmap_item.setTransformOriginPoint(self.placeholder_image.width() / 2, self.placeholder_image.height() / 2)
        self.pixmap_item.setPos(640 - self.placeholder_image.width() / 2, 360 - self.placeholder_image.height() / 2)
        self.pixmap_item.setToolTip("Test Mouseover")

        # Timer for frame update
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_render)
        self.timer.setInterval(16) # 60FPS
        self.timer.start()

    def update_render(self):
        # Scale the scene view
        self.view.resetTransform() 
        self.view.scale(self.zoom_slider.value() / 100, self.zoom_slider.value() / 100)

        # Rotate the image
        self.pixmap_item.setRotation(self.angle)
        self.angle += (self.slider.value() / 100)
        if self.angle >= 360:
            self.angle = 0



if __name__ == "__main__":
    print(os.getcwd())
    app = QApplication(sys.argv)
    app.setStyleSheet("QLabel { color: white; } QWidget { background-color: black; }")

    window = MainWindow()
    window.show()
    _ = input() # don't exit until enter is pressed
    