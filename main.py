from collections import deque
import os, sys, yaml, time, threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QTransform, QPainter, QPen, QColor, QBrush
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QSlider, QVBoxLayout, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem, QGraphicsEllipseItem, QPushButton, QButtonGroup, QHBoxLayout, QGraphicsPolygonItem

WINDOW_X_SIZE = 1280
WINDOW_Y_SIZE = 680
ASSET_RESOLUTION = 400 # images are 400px by 400px
GRAV = 6.6743 * 10**-11
FPS = 60
SUN_MASS = 1.989 * 10 ** 30 # this should probably go in a file somewhere
TICKS_PER_FRAME = 16 # update physics 16x per frame

RED = QColor(255, 0, 0, 50)
BLUE = QColor(0, 0, 255, 50)

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
    def __init__(self, name, posx, posy, vx, vy, radius, image_path, moons, mass=0):
        # TODO: add tail to the comet
        self.name = name
        self.posx, self.posy = posx, posy
        self.vx, self.vy = vx, vy
        self.radius = radius # this is the radius of the planet itself, NOT orbit
        if image_path:
            self.graphics_item = QGraphicsPixmapItem(QPixmap(image_path))
        else:
            self.graphics_item = QGraphicsPixmapItem(QPixmap("./assets/planet_placeholder.png"))
        self.moons = []
        for moon in moons:
            self.moons.append(Moon(moon['name'], self.posx + moon['apoapsis'], 0, 0, self.vy + moon['initial_speed'], moon['radius'], None))
        self.mass = mass
        # TODO: on right click, set view to follow planet
        self.graphics_item.setToolTip(self.name)
    
class Moon:
    def __init__(self, name, posx, posy, vx, vy, radius, image_path):
        self.name = name
        self.posx, self.posy = posx, posy
        self.vx, self.vy = vx, vy
        self.radius = radius # this is the radius of the planet itself, NOT orbit
        if image_path:
            self.graphics_item = QGraphicsPixmapItem(QPixmap(image_path))
        else:
            self.graphics_item = QGraphicsPixmapItem(QPixmap("./assets/planet_placeholder.png"))
        self.graphics_item.setToolTip(self.name)


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

        # Visualize Kepler's 2nd Law
        self.pen = QPen(RED)
        self.next_pen_color = BLUE
        self.number_of_kepler_updates = 0
        self.selected_kepler_object = "None"
        self.kepler_lines = deque()
        
        # Visualize planet layers
        self.selected_layers_object = "None"
        self.previous_concentric_circles = []

        # Visualize comet tail
        self.comet_tail = []
        self.comet_tail_pen = QPen(QColor(Qt.white), 3)

        # Canvas for drawing
        self.view = QGraphicsView(self)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, WINDOW_X_SIZE, WINDOW_Y_SIZE)
        self.view.setScene(self.scene)
        self.view.setFixedSize(WINDOW_X_SIZE, WINDOW_Y_SIZE)
        self.view.setRenderHints(QPainter.SmoothPixmapTransform & ~QPainter.Antialiasing)
        layout.addWidget(self.view)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    
        # TODO: star background currently has north star as center but it should actually be
        # 23.5 degrees off (bc of earth's axial tilt)
        # can also adjust earth similarly
        self.background = QGraphicsPixmapItem(QPixmap('./assets/bg_stars.png'))
        self.scene.addItem(self.background)
        self.background.setPos(0,0)

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
        self.zoom_slider.setRange(1, 2000) # tweak this
        self.zoom_slider.setValue(100)
        layout.addWidget(self.zoom_slider)


        self.sun = Sun(695_508_000, './assets/sun.png')
        self.scene.addItem(self.sun.graphics_item)
        
        self.planets = []
        with open('planets.yml', 'r') as f:
            data = yaml.safe_load(f)
            for planet in data:
                self.planets.append(Planet(planet['name'], planet['aphelion'], 0, 0, planet['initial_speed'], planet['radius'], planet['image'], planet.get('moons', [])))
        for planet in self.planets:
            self.scene.addItem(planet.graphics_item)
            for moon in planet.moons:
                self.scene.addItem(moon.graphics_item)

        with open('./assets/planet_layers_specs.yml', 'r') as f:
            self.planets_composition_data = yaml.safe_load(f)

        layout.addWidget(QLabel("Show Kepler's 2nd Law"))
        button_layout = QHBoxLayout()
        button_group = QButtonGroup(self)

        button = QPushButton("None")
        button.setCheckable(True)
        button.setStyleSheet("QPushButton {color: black; background-color: white;}")
        button_group.addButton(button)
        button_layout.addWidget(button)
        button.setChecked(True)

        for planet in self.planets:
            button = QPushButton(planet.name)
            button.setCheckable(True)
            button.setStyleSheet("QPushButton {color: black; background-color: white;}")
            button_group.addButton(button)
            button_layout.addWidget(button)

        layout.addLayout(button_layout)
        button_group.buttonClicked.connect(self.kepler_button_clicked)

        layout.addWidget(QLabel("Show Layers"))
        button_layout = QHBoxLayout()
        button_group = QButtonGroup(self)

        button = QPushButton("None")
        button.setCheckable(True)
        button.setStyleSheet("QPushButton {color: black; background-color: white;}")
        button_group.addButton(button)
        button_layout.addWidget(button)
        button.setChecked(True)

        for planet in self.planets[:-1]:
            button = QPushButton(planet.name)
            button.setCheckable(True)
            button.setStyleSheet("QPushButton {color: black; background-color: white;}")
            button_group.addButton(button)
            button_layout.addWidget(button)

        layout.addLayout(button_layout)
        button_group.buttonClicked.connect(self.layers_button_clicked)

        layout.addWidget(QLabel("Follow"))
        button_layout = QHBoxLayout()
        button_group = QButtonGroup(self)

        button = QPushButton("Sun")
        button.setCheckable(True)
        button.setStyleSheet("QPushButton {color: black; background-color: white;}")
        button_group.addButton(button)
        button_layout.addWidget(button)
        button.setChecked(True)

        for planet in self.planets:
            button = QPushButton(planet.name)
            button.setCheckable(True)
            button.setStyleSheet("QPushButton {color: black; background-color: white;}")
            button_group.addButton(button)
            button_layout.addWidget(button)

        layout.addLayout(button_layout)
        button_group.buttonClicked.connect(self.follow_planet)

        self.selected_follow_object = "Sun"

        self.real_world_delta_time = -1
        self.real_world_time = time.perf_counter()

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update_frame)
        self.frame_timer.setInterval(1000 / FPS) # 1000 ms / 60 FPS = 16.67 ms
        self.frame_timer.start()
    
    def kepler_button_clicked(self, button):
        self.selected_kepler_object = button.text()
        
        if self.selected_kepler_object == "None":
            self.number_of_kepler_updates = 0
            for _ in range(len(self.kepler_lines)):
                self.scene.removeItem(self.kepler_lines.popleft())

    def layers_button_clicked(self, button):
        self.selected_layers_object = button.text()

        if self.selected_layers_object == "None":
            for _ in range(len(self.previous_concentric_circles)):
                self.scene.removeItem(self.previous_concentric_circles.pop())
        
    def follow_planet(self, button):
        self.selected_follow_object = button.text()
        print(self.selected_follow_object)

    def update_physics(self):
        # physics updates
        # DON'T draw anything in this function, it will be too slow
        current_time = time.perf_counter()
        self.real_world_delta_time =  current_time - self.real_world_time
        self.real_world_time = current_time

        time_scale = self.time_slider.value()
        time_step = time_scale * self.real_world_delta_time
        
        for planet in self.planets:
            # move planet
            planet.posx += planet.vx * time_step
            planet.posy += planet.vy * time_step

            # apply acceleration to planet
            accel = get_accel_vector(SUN_MASS, planet.posx, planet.posy)

            # apply acceleration to moons
            for moon in planet.moons:
                moon.posx += moon.vx * time_step
                moon.posy += moon.vy * time_step
                accel_sun = get_accel_vector(SUN_MASS, moon.posx, moon.posy)
                # print('###')
                # print(accel_sun)
                moon.vx += accel_sun[0] * time_step
                moon.vy += accel_sun[1] * time_step
                # print(moon.posx, planet.posx)
                # print(moon.posy, planet.posy)
                accel_planet = get_accel_vector(planet.mass, moon.posx - planet.posx, moon.posy - planet.posy)
                # print(accel_planet)
                moon.vx += accel_planet[0] * time_step
                moon.vy += accel_planet[1] * time_step


            planet.vx += accel[0] * time_step
            planet.vy += accel[1] * time_step
            # there's a trick where applying half the acceleration before moving and half after gives a better approximation if time_step changes
            # may be worth doing if our sim isn't precise enough
    
    def update_frame(self):
        # draw updates
        # DON'T do any physics in this function, modify update_physics() instead

        # Scale the scene view
        m_per_px = 10_000_000_000_000 / WINDOW_Y_SIZE / (self.zoom_slider.value()/100)

        planet_scale = self.planet_scale_slider.value()
        sun_scale = self.sun_scale_slider.value()

        # scale sun
        scale_of_sun = self.sun.radius * 2 * sun_scale / m_per_px / ASSET_RESOLUTION
        sun_x = WINDOW_X_SIZE / 2.0 - ASSET_RESOLUTION * scale_of_sun / 2.0
        sun_y = WINDOW_Y_SIZE / 2.0 - ASSET_RESOLUTION * scale_of_sun / 2.0
        self.sun.graphics_item.setScale(scale_of_sun)
        self.sun.graphics_item.setPos(sun_x, sun_y)

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
            # TODO: planet rotation?
            
            if planet.name == "Comet":
                self.draw_comet_tail(sun_x + self.sun.graphics_item.boundingRect().width() * scale_of_sun / 2.0, sun_y + bounding_rect.height() * scale_of_sun / 2.0, x + bounding_rect.width() * scale / 2.0, y + bounding_rect.height() * scale / 2.0)

            if planet.name == self.selected_layers_object: 
                self.draw_planet_layers(planet.name, x, y, bounding_rect.width() * scale, bounding_rect.height() * scale)

            if planet.name == self.selected_kepler_object:
                new_line = QGraphicsLineItem(sun_x + self.sun.graphics_item.boundingRect().width() * scale_of_sun / 2.0, sun_y + bounding_rect.height() * scale_of_sun / 2.0, x + bounding_rect.width() * scale / 2.0, y + bounding_rect.height() * scale / 2.0)
                self.kepler_lines.append(new_line)

                new_line.setPen(self.pen)
                self.scene.addItem(new_line)

                if len(self.kepler_lines) > 120:
                    self.scene.removeItem(self.kepler_lines.popleft())
                
                if self.number_of_kepler_updates == 60:
                    self.pen.setColor(self.next_pen_color) 
                    self.next_pen_color = RED if self.next_pen_color == BLUE else BLUE
                    self.number_of_kepler_updates = 0
            
                self.number_of_kepler_updates += 1
            
            for moon in planet.moons:
                scale = moon.radius * 2 * planet_scale / m_per_px / ASSET_RESOLUTION
                moon.graphics_item.setScale(scale)
                bounding_rect = moon.graphics_item.boundingRect() # can probably just use ASSET_RESOLUTION for this, I'm just not sure if that will still work with rotation if we add that
                x = WINDOW_X_SIZE / 2.0 + moon.posx / m_per_px - bounding_rect.width() * scale / 2.0
                y = WINDOW_Y_SIZE / 2.0 + moon.posy / m_per_px - bounding_rect.height() * scale / 2.0
                moon.graphics_item.setPos(x, y)
        
        if self.selected_follow_object == 'Sun':
            for item in self.scene.items():
                item.resetTransform()
        else:
            for planet in self.planets:
                if planet.name == self.selected_follow_object:
                    transform = QTransform()
                    scale = planet.radius * 2 * planet_scale / m_per_px / ASSET_RESOLUTION
                    bounding_rect = planet.graphics_item.boundingRect()
                    x = planet.posx / m_per_px - bounding_rect.width() * scale / 2.0
                    y = planet.posy / m_per_px - bounding_rect.height() * scale / 2.0
                    transform.translate(-x, -y)
                    for item in self.scene.items():
                        if item != self.background:
                            item.setTransform(transform)

    def draw_comet_tail(self, sun_x, sun_y, curr_x, curr_y):
        if self.comet_tail:
            for _ in range(len(self.comet_tail)):
                self.scene.removeItem(self.comet_tail.pop())

        unit_direction_x = curr_x - sun_x
        unit_direction_y = curr_y - sun_y

        magnitude = (unit_direction_x ** 2 + unit_direction_y ** 2) ** 0.5
        unit_direction_x /= magnitude
        unit_direction_y /= magnitude

        for spacing_x, spacing_y in [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3)]:
            line = QGraphicsLineItem(curr_x + spacing_x, curr_y + spacing_y, curr_x + unit_direction_x * 70, curr_y + unit_direction_y * 70)
            line.setPen(self.comet_tail_pen)
            self.comet_tail.append(line)
            self.scene.addItem(line)

    def draw_planet_layers(self, planet, outermost_x, outermost_y, outermost_width, outermost_height):
        if self.previous_concentric_circles:
            for _ in range(len(self.previous_concentric_circles)):
                self.scene.removeItem(self.previous_concentric_circles.pop())

        thicknesses, colors, layers = [], [], []
        total_thickness = 0
        for layer, description in self.planets_composition_data[planet].items():
            t, c = int(description["Thickness"]), description["Color"]
            total_thickness += t
            thicknesses.append(total_thickness)
            colors.append(QColor(c))
            layers.append(layer)
        
        # Must reverse order in order for inner layers to be drawn on top of outer layers
        thicknesses.reverse()
        layers.reverse()
        colors.reverse()

        for i, t in enumerate(thicknesses):
            p = (t / total_thickness) 
            inner_width, inner_height = p * outermost_width, p * outermost_height
            inner_x, inner_y = outermost_x + outermost_width / 2 - inner_width / 2, outermost_y + outermost_height / 2 - inner_height / 2
            
            new_circle = QGraphicsEllipseItem(inner_x, inner_y, inner_width, inner_height)
            new_circle.setBrush(QBrush(colors[i]))
            new_circle.setPen(QPen(colors[i]))
            new_circle.setToolTip(layers[i])
            
            self.previous_concentric_circles.append(new_circle)
            self.scene.addItem(new_circle)

    def physics_loop(self, kill_flag):
        while not kill_flag.is_set():
            self.update_physics()
            time.sleep(0.0002)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QLabel { color: white; } QWidget { background-color: black; }")
    window = MainWindow()
    window.show()
    physics_kill_flag = threading.Event()
    physics_thread = threading.Thread(target=window.physics_loop, args = (physics_kill_flag,))
    physics_thread.start()
    app.exec()
    physics_kill_flag.set()
    sys.exit()
    