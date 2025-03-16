import os, sys, yaml, time
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QPaintEvent, QPixmap, QTransform, QPainter
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QSlider, QVBoxLayout, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem

WINDOW_X_SIZE = 1280
WINDOW_Y_SIZE = 720
ASSET_RESOLUTION = 400 # images are 400px by 400px
GRAV = 6.6743 * 10**-11
FPS = 60
SUN_MASS = 1.989 * 10 ** 30 # this should probably go in a file somewhere
TICKS_PER_FRAME = 16 # update physics 16x per frame

# since QGraphicsView lets us transform the scale this might as well be a constant
m_per_px = 10_000_000_000_000 / WINDOW_Y_SIZE 

# upscale relevant objects by these factors since space is big and everything is invisibly small by comparison
sun_scale = 100
planet_scale = 5000

default_time_scale = 3_000_000

def get_accel_vector(mass, x_disp, y_disp):
    # g = GM/(R^2)
    distance_squared = x_disp * x_disp + y_disp * y_disp
    distance = distance_squared ** 0.5
    acc_mag = mass * GRAV / distance_squared
    return (acc_mag * -x_disp / distance, acc_mag * -y_disp / distance) # x and y components of accel vector



class Planet:
    def __init__(self, posx, posy, vx, vy, radius, image_path = None):
        self.posx, self.posy = posx, posy
        self.vx, self.vy = vx, vy
        self.radius = radius # this is the radius of the planet itself, NOT orbit
        if image_path:
            self.graphics_item = QGraphicsPixmapItem(QPixmap(image_path))
        else:
            self.graphics_item = QGraphicsPixmapItem(QPixmap("./assets/planet_placeholder.png"))

class Sun: # honestly this probably doesn't even need to be a class, might clean up later
    def __init__(self, radius, image_path = None):
        self.radius = radius
        if image_path:
            self.graphics_item = QGraphicsPixmapItem(QPixmap(image_path))
        else:
            self.graphics_item = QGraphicsPixmapItem(QPixmap("./assets/planet_placeholder.png"))
 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("P20A Final Proj Solar System Sim")

        # Create central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)

        # Canvas for drawing
        self.view = QGraphicsView(self)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, WINDOW_X_SIZE, WINDOW_Y_SIZE)
        self.view.setScene(self.scene)
        self.view.setFixedSize(WINDOW_X_SIZE, WINDOW_Y_SIZE)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        layout.addWidget(self.view)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # QSlider to control sun_scale
        layout.addWidget(QLabel("Sun Scale"))
        self.sun_scale_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.sun_scale_slider.setRange(0, sun_scale * 10)
        self.sun_scale_slider.setValue(sun_scale)
        layout.addWidget(self.sun_scale_slider)

        # QSlider to control planet_scale
        layout.addWidget(QLabel("Planet Scale"))
        self.planet_scale_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.planet_scale_slider.setRange(0, planet_scale * 10)
        self.planet_scale_slider.setValue(planet_scale)
        layout.addWidget(self.planet_scale_slider)

        # QSlider to control time warp
        layout.addWidget(QLabel("Time Scale"))
        self.time_slider = QSlider(Qt.Horizontal, self)
        self.time_slider.setRange(0, default_time_scale * 10) # max speed is about 1 year per second
        self.time_slider.setValue(default_time_scale)
        layout.addWidget(self.time_slider)

        # QSlider to control zoom
        layout.addWidget(QLabel("Zoom"))
        self.zoom_slider = QSlider(Qt.Horizontal, self)
        self.zoom_slider.setRange(1, 1000) # tweak this
        self.zoom_slider.setValue(100)
        layout.addWidget(self.zoom_slider)

        # TODO: remove this
        # Load the placeholder image
        # self.placeholder_image = QPixmap("./assets/sol_placeholder.png")
        # self.angle = 0
        # self.pixmap_item = QGraphicsPixmapItem(self.placeholder_image)
        # self.scene.addItem(self.pixmap_item)
        # self.pixmap_item.setTransformOriginPoint(self.placeholder_image.width() / 2, self.placeholder_image.height() / 2)
        # self.pixmap_item.setPos(640 - self.placeholder_image.width() / 2, 360 - self.placeholder_image.height() / 2)
        # self.pixmap_item.setToolTip("Test Mouseover")


        self.sun = Sun(695_508_000, './assets/sun.png')
        self.scene.addItem(self.sun.graphics_item)
        
        self.planets = []
        with open('planets.yml', 'r') as f:
            data = yaml.safe_load(f)
            for planet in data:
                self.planets.append(Planet(planet['aphelion'], 0, 0, planet['initial_speed'], planet['radius'], planet['image']))
        for planet in self.planets:
            self.scene.addItem(planet.graphics_item)

        # Timer for physics update
        # TODO: consider using an approach that allows even shorter timer
        # physics currently run in about 15 us just fine, but QTimer doesn't support delays smaller than 1000 us
        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self.update_physics)
        self.physics_timer.setInterval(1000 / FPS / TICKS_PER_FRAME) # 1000 ms / 60 FPS / 16 TICKS_PER_FRAME ~= 1 ms
        self.physics_timer.start()

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update_frame)
        self.frame_timer.setInterval(1000 / FPS) # 1000 ms / 60 FPS = 16.67 ms
        self.frame_timer.start()
    
    def update_physics(self):
        # physics updates
        # DON'T draw anything in this function, it will be too slow

        time_scale = self.time_slider.value()
        time_step = time_scale * (self.physics_timer.interval() / 1000) 
        
        for planet in self.planets:
            # move planet
            planet.posx += planet.vx * time_step
            planet.posy += planet.vy * time_step

            # apply acceleration to planet
            accel = get_accel_vector(SUN_MASS, planet.posx, planet.posy)
            planet.vx += accel[0] * time_step
            planet.vy += accel[1] * time_step
            # there's a trick where applying half the acceleration before moving and half after gives a better approximation
            # may be worth doing if our sim isn't precise enough
    
    def update_frame(self):
        # draw updates
        # DON'T do any physics in this function, modify update_physics() instead

        # Scale the scene view
        self.view.resetTransform() # scale is relative to previous scale, so need to reset or it grows/shrinks again on each frame
        self.view.scale(self.zoom_slider.value() / 100, self.zoom_slider.value() / 100)

        planet_scale = self.planet_scale_slider.value()
        sun_scale = self.sun_scale_slider.value()

        # scale sun
        scale = self.sun.radius * 2 * sun_scale / m_per_px / ASSET_RESOLUTION
        self.sun.graphics_item.setScale(self.sun.radius * 2 * sun_scale / m_per_px / ASSET_RESOLUTION)
        bounding_rect = self.sun.graphics_item.boundingRect()
        self.sun.graphics_item.setPos(QPoint(WINDOW_X_SIZE / 2 - bounding_rect.width() * scale / 2, WINDOW_Y_SIZE / 2 - bounding_rect.height() * scale / 2)) # TODO: might need to adjust this depending on how we implement follow/zoom

        for planet in self.planets:
            # scale planet
            scale = planet.radius * 2 * planet_scale / m_per_px / ASSET_RESOLUTION
            planet.graphics_item.setScale(scale)

            # calculate planet coordinates on canvas
            bounding_rect = planet.graphics_item.boundingRect() # can probably just use ASSET_RESOLUTION for this, I'm just not sure if that will still work with rotation if we add that
            x = WINDOW_X_SIZE / 2.0 + planet.posx / m_per_px - bounding_rect.width() * scale / 2.0
            y = WINDOW_Y_SIZE / 2.0 + planet.posy / m_per_px - bounding_rect.height() * scale / 2.0

            # move planet graphic
            planet.graphics_item.setPos(x, y)
            





if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QLabel { color: white; } QWidget { background-color: black; }")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    