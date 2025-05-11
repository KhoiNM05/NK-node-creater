import sys
import sqlite3
from PyQt6.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, 
    QGraphicsPolygonItem, QInputDialog, QGraphicsEllipseItem, QGraphicsTextItem,
    QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QMainWindow
)
from PyQt6.QtGui import QPixmap, QPen, QBrush, QPolygonF, QColor
from PyQt6.QtCore import Qt, QPointF
import uuid

class GraphEditor(QGraphicsView):
    def __init__(self, image_path, db_path="graph.db"):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.undo_stack = []
        self.image_path = image_path
        self.db_path = db_path
        
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.init_db()
        
        pixmap = QPixmap(image_path)
        self.map_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.map_item)
        self.zoom_factor = 1.0
        self.max_zoom = 3.0
        self.min_zoom = 0.5
        self.nodes = {}
        # self.edges = [] # Replaced by self.edges_data
        self.edges_data = [] # Stores {'from': n1, 'to': n2, 'weight': w, 'type': 'normal'/'car'}
        self.is_panning = False
        self.last_pan_point = None
        self.selected_nodes = [] 
        
        self.special_place_mode = False
        self.special_places = {}
        self.sidebar_updater = None # To link with sidebar button state

        self.car_mode = False # For car-specific edge weights
        self.car_mode_button_updater = None # To link with sidebar button state for car mode

        self.load_graph()

    def set_special_place_mode(self, enabled):
        if self.special_place_mode == enabled:
            return 
        self.special_place_mode = enabled
        if self.special_place_mode:
            print("Special Place Mode: ON. Left-click to add a named special place.")
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            print("Special Place Mode: OFF. Normal node/edge editing.")
            self.unsetCursor()
        
        if self.sidebar_updater:
            self.sidebar_updater(self.special_place_mode)

    def toggle_special_place_mode(self):
        self.set_special_place_mode(not self.special_place_mode)

    def set_car_mode(self, enabled):
        if self.car_mode == enabled:
            return
        self.car_mode = enabled
        if self.car_mode:
            print("Car Mode: ON. New edges will be 'car' type with modified weight (3/5 of normal).")
        else:
            print("Car Mode: OFF. New edges will be 'normal' type with normal weight.")
        
        if self.car_mode_button_updater:
            self.car_mode_button_updater(self.car_mode)

    def toggle_car_mode(self):
        self.set_car_mode(not self.car_mode)
    
    def init_db(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                name TEXT PRIMARY KEY,
                x REAL,
                y REAL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                node_from TEXT,
                node_to TEXT,
                weight REAL,
                PRIMARY KEY (node_from, node_to),
                FOREIGN KEY (node_from) REFERENCES nodes(name),
                FOREIGN KEY (node_to) REFERENCES nodes(name)
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS special_places (
                id TEXT PRIMARY KEY,
                custom_name TEXT,
                x REAL,
                y REAL
            )
        """)
        self.conn.commit()
    def remove_edge(self, edge):
        # edge is a tuple (node_from, node_to)
        # To correctly undo, we need to store its original weight.
        # We need to find the edge in self.edges to remove it,
        # and fetch its weight from the DB for the undo stack.

        # Check if the edge (node_from, node_to) exists in self.edges (which stores (from, to) tuples)
        if edge not in self.edges:
            # Attempt to find if it's stored in reverse for undirected representation if any
            reversed_edge = (edge[1], edge[0])
            if reversed_edge in self.edges:
                edge_to_remove_from_list = reversed_edge
            else:
                print(f"Edge {edge[0]} -> {edge[1]} not found in memory for removal.")
                return # Or handle as an error
        else:
            edge_to_remove_from_list = edge
        
        # Fetch weight from DB
        self.cursor.execute("SELECT weight FROM edges WHERE node_from = ? AND node_to = ?", (edge[0], edge[1]))
        result = self.cursor.fetchone()
        if not result:
            # Try reverse if not found (in case DB stores undirected edges one way)
            self.cursor.execute("SELECT weight FROM edges WHERE node_from = ? AND node_to = ?", (edge[1], edge[0]))
            result = self.cursor.fetchone()
            if not result:
                print(f"Edge {edge[0]} -> {edge[1]} not found in DB for weight retrieval.")
                # Fallback or error, for now, let's assume 0 if not found, though this indicates inconsistency
                original_weight = 0 
            else:
                original_weight = result[0]
        else:
            original_weight = result[0]

        self.undo_stack.append(("remove_edge", edge, original_weight)) # Store original weight
        
        if edge_to_remove_from_list in self.edges:
            self.edges.remove(edge_to_remove_from_list)
        
        # Delete from DB (try both directions if your DB might store undirected edges one way)
        self.cursor.execute("DELETE FROM edges WHERE (node_from = ? AND node_to = ?) OR (node_from = ? AND node_to = ?)", 
                            (edge[0], edge[1], edge[1], edge[0]))
        self.conn.commit()
        print(f"Edge removed: {edge[0]} -> {edge[1]} (Weight: {original_weight})")
        self.redraw_graph() 
    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())

        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier and event.button() == Qt.MouseButton.LeftButton:
            self.is_panning = True 
            self.last_pan_point = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor) 
            return 

        if self.special_place_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                custom_name, ok = QInputDialog.getText(self, "Special Place Name", "Enter name for the special place:")
                if ok and custom_name:
                    place_id = f"SP_{uuid.uuid4().hex[:8]}"
                    scene_pos = self.mapToScene(event.pos()) # Use scene_pos consistently
                    self.special_places[place_id] = {'name': custom_name, 'x': scene_pos.x(), 'y': scene_pos.y()}
                    self.cursor.execute("INSERT INTO special_places (id, custom_name, x, y) VALUES (?, ?, ?, ?)",
                                        (place_id, custom_name, scene_pos.x(), scene_pos.y()))
                    self.conn.commit()
                    self.draw_special_place(scene_pos, custom_name, place_id) # Use scene_pos
                    self.undo_stack.append(("special_place_added", place_id, custom_name, scene_pos.x(), scene_pos.y()))
                    print(f"Special place added: {custom_name} ({place_id}) at {scene_pos.x()}, {scene_pos.y()}")
            return 

        # Normal mode (not special_place_mode and not panning)
        if event.button() == Qt.MouseButton.LeftButton:
            self.cursor.execute("SELECT COUNT(*) FROM nodes WHERE x = ? and y = ?", (pos.x(), pos.y()))
            exists = self.cursor.fetchone()[0]
            if exists:
                print("A node already exists at this exact position.") 
                return 
            
            node_name = f"N{uuid.uuid4().hex[:6]}"
            self.nodes[node_name] = (pos.x(), pos.y())
            self.undo_stack.append(("node_added", node_name, pos.x(), pos.y())) 
            self.cursor.execute("INSERT INTO nodes (name, x, y) VALUES (?, ?, ?)", (node_name, pos.x(), pos.y()))
            self.conn.commit()
            self.draw_node(pos, node_name)
            print(f"Node added: {node_name} at {pos.x()}, {pos.y()}")
        elif event.button() == Qt.MouseButton.RightButton:
            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                # Try to remove special place first with Shift + Right Click
                clicked_special_place_id = self.find_closest_special_place(pos, tolerance=15) # Increased tolerance for special places
                if clicked_special_place_id:
                    self.remove_special_place(clicked_special_place_id)
                    return # Handled

                # If no special place, try to remove edge or node
                clicked_edge = self.find_clicked_edge(pos)
                if clicked_edge:
                    self.remove_edge(clicked_edge)
                else:
                    closest_node = self.find_closest_node(pos, tolerance=10) # Standard tolerance for nodes
                    if closest_node:
                        self.remove_node(closest_node)
            else: # Normal Right Click (no shift)
                closest_node = self.find_closest_node(pos)
                if closest_node:
                    if closest_node not in self.selected_nodes: 
                        self.selected_nodes.append(closest_node)
                        print(f"Selected node: {closest_node}")
                    if len(self.selected_nodes) == 2:
                        self.create_edge(self.selected_nodes[0], self.selected_nodes[1])
                        self.selected_nodes.clear()
        else:
            super().mousePressEvent(event)
    
    def remove_special_place(self, place_id):
        if place_id not in self.special_places:
            print(f"Special place {place_id} not found for removal.")
            return

        place_data = self.special_places[place_id]
        self.undo_stack.append(("special_place_removed", place_id, place_data))

        del self.special_places[place_id]
        self.cursor.execute("DELETE FROM special_places WHERE id = ?", (place_id,))
        self.conn.commit()

        print(f"Special place removed: {place_data.get('name', place_id)}")
        self.redraw_graph()

    def find_closest_special_place(self, pos, tolerance=10):
        min_dist_sq = tolerance ** 2 # Use squared distance to avoid sqrt
        closest_place_id = None
        for place_id, data in self.special_places.items():
            dist_sq = (pos.x() - data['x']) ** 2 + (pos.y() - data['y']) ** 2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_place_id = place_id
        return closest_place_id

    def remove_node(self, node_name):
        if node_name not in self.nodes:
            return

        node_x, node_y = self.nodes[node_name]
        # Find all edges connected to this node to add to undo stack
        edges_to_remove_for_undo = []
        for edge in list(self.edges): # Iterate over a copy for safe removal
            if edge[0] == node_name or edge[1] == node_name:
                edges_to_remove_for_undo.append(edge)
        
        self.undo_stack.append(("node_removed", node_name, node_x, node_y, edges_to_remove_for_undo))

        # Xóa node khỏi database
        self.cursor.execute("DELETE FROM nodes WHERE name = ?", (node_name,))
        self.cursor.execute("DELETE FROM edges WHERE node_from = ? OR node_to = ?", (node_name, node_name))
        self.conn.commit()

        # Xóa node và các cạnh liên quan khỏi bộ nhớ
        del self.nodes[node_name]
        for edge in edges_to_remove_for_undo:
            if edge in self.edges:
                self.edges.remove(edge)

        print(f"Node {node_name} removed.")
        self.redraw_graph()

        
    def draw_node(self, pos, label):
        pen = QPen(Qt.GlobalColor.black)
        brush = QBrush(Qt.GlobalColor.green)
        self.scene.addEllipse(pos.x() - 5, pos.y() - 5, 10, 10, pen, brush)
    
    def create_edge(self, node1, node2):
        if any(e == (node1, node2) or e == (node2, node1) for e in self.edges): # Check for existing edge (undirected)
            print(f"Edge {node1} - {node2} already exists.")
            return
        if node1 not in self.nodes or node2 not in self.nodes:
            print(f"Cannot create edge: one or both nodes do not exist ({node1}, {node2}).")
            return

        x1, y1 = self.nodes[node1]
        x2, y2 = self.nodes[node2]
        
        weight = self.calculate_weight(node1, node2)
        edge_description = "normal"
        if self.car_mode:
            weight = (weight * 3) / 5
            edge_description = "car mode (3/5 weight)"
            print(f"Creating edge in Car Mode: Original Weight {self.calculate_weight(node1, node2):.2f}, Modified Weight: {weight:.2f}")


        pen = QPen(Qt.GlobalColor.blue, 2) # Default color
        # if self.car_mode: # Optional: different color for car mode edges
        #     pen = QPen(QColor("orange"), 2) 

        self.scene.addLine(x1, y1, x2, y2, pen)
        arrow_size = 10
        direction = QPointF(x2-x1, y2-y1)
        length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if length == 0:
            return
        unit_direction = QPointF(direction.x() / length, direction.y()/ length)
        arrow_point = QPointF(x2,y2) - unit_direction * arrow_size
        perp = QPointF(-unit_direction.y(), unit_direction.x())
        p1 = arrow_point + perp * (arrow_size / 2)
        p2 = arrow_point - perp * (arrow_size / 2)
        arrow_head = QPolygonF([QPointF(x2, y2) , p1, p2])
        arrow_item = QGraphicsPolygonItem(arrow_head)
        arrow_item.setBrush(QBrush(Qt.GlobalColor.blue)) # Match pen color or car_mode color
        # if self.car_mode:
        #     arrow_item.setBrush(QBrush(QColor("orange")))
        self.scene.addItem(arrow_item)

        self.edges.append((node1, node2)) # Storing as (from, to)
        
        self.cursor.execute("INSERT INTO edges (node_from, node_to, weight) VALUES (?, ?, ?)", (node1, node2, weight))
        self.conn.commit()
        self.undo_stack.append(("edge_added", node1, node2, weight)) 
        print(f"Edge added: {node1} -> {node2} with {edge_description} weight: {weight:.2f}")
    def calculate_weight(self,node1, node2):
        x1, y1 = self.nodes[node1]
        x2, y2 = self.nodes[node2]
        return round(((x2-x1) ** 2 + (y2- y1)**2) ** 0.5 /100, 4)
    def find_closest_node(self, pos, tolerance=10): # Added tolerance parameter
        min_dist_sq = tolerance ** 2 # Compare squared distances
        closest_node = None
        for node, (x, y) in self.nodes.items():
            dist_sq = (pos.x() - x) ** 2 + (pos.y() - y) ** 2 # Squared distance
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_node = node
        return closest_node
    def find_clicked_edge(self, pos):
        click_tolerance = 5  # Increased tolerance slightly for easier clicking

        for node1, node2 in self.edges:
            if node1 not in self.nodes or node2 not in self.nodes:
                continue

            x1, y1 = self.nodes[node1]
            x2, y2 = self.nodes[node2]

            if x2 - x1 != 0:
                m = (y2 - y1) / (x2 - x1)  # Hệ số góc
                exp_y = m * (pos.x() - x1) + y1
            else:
                exp_y = y1  # Trường hợp đường thẳng đứng

            # Kiểm tra nếu pos gần cạnh
            if abs(pos.y() - exp_y) < click_tolerance and min(x1, x2) <= pos.x() <= max(x1, x2):
                print(f"Clicked on edge: {node1} -> {node2}")
                return (node1, node2)
        return None
    def wheelEvent(self,event):
        zoom_factor = 1.15  # Hệ số zoom
        min_scale = 0.2  # Giới hạn thu nhỏ
        max_scale = 5.0  # Giới hạn phóng to

        old_pos = self.mapToScene(event.position().toPoint())  # Lưu vị trí trước zoom

        current_scale = self.transform().m11()

        if event.angleDelta().y() > 0:  # Zoom in
            new_scale = min(current_scale * zoom_factor, max_scale)
        else:  # Zoom out
            new_scale = max(current_scale / zoom_factor, min_scale)
        scale_factor = new_scale/ current_scale
         
        transform = self.transform()
        transform.scale(scale_factor, scale_factor)
        self.setTransform(transform)

        new_pos = self.mapToScene(event.position().toPoint())  # Lấy vị trí sau zoom

        # Di chuyển màn hình để giữ điểm dưới con trỏ không thay đổi
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())
    def load_graph(self):
        self.cursor.execute("SELECT * FROM nodes")
        self.nodes = {row[0]: (row[1], row[2]) for row in self.cursor.fetchall()}
        self.cursor.execute("SELECT node_from, node_to, weight FROM edges") # Ensure weight is loaded if needed by self.edges
        # Current self.edges only stores (from, to). If it stored weight, this would change.
        self.edges = [(row[0], row[1]) for row in self.cursor.fetchall()]
        
        self.cursor.execute("SELECT id, custom_name, x, y FROM special_places")
        self.special_places = {row[0]: {'name': row[1], 'x': row[2], 'y': row[3]} for row in self.cursor.fetchall()}
        
        self.redraw_graph()
    
    def redraw_graph(self):
        self.scene.clear()
        # Re-add map item
        self.map_item = QGraphicsPixmapItem(QPixmap(self.image_path)) # Ensure map_item is current
        self.scene.addItem(self.map_item)

        for node, (x, y) in self.nodes.items():
            self.draw_node(QPointF(x, y), node)
        
        # To draw edges with specific colors for car_mode, we'd need to know their type/weight here.
        # Currently, self.edges only has (from, to). We'd need to fetch weight/type from DB or store more in self.edges.
        # For now, all edges are drawn the same.
        for node1, node2 in self.edges: 
            if node1 in self.nodes and node2 in self.nodes: 
                x1, y1 = self.nodes[node1]
                x2, y2 = self.nodes[node2]
                
                # Default pen
                pen = QPen(Qt.GlobalColor.blue, 2)
                brush = QBrush(Qt.GlobalColor.blue)

                # If you want to visually distinguish car_mode edges, you'd need to:
                # 1. Store edge type or modified weight in self.edges or fetch from DB here.
                # For example, if self.edges stored (n1, n2, weight, type):
                # self.cursor.execute("SELECT node_from, node_to, weight, type FROM edges")
                # And then:
                # if edge_type == 'car':
                #    pen = QPen(QColor("orange"), 2)
                #    brush = QBrush(QColor("orange"))
                
                self.scene.addLine(x1, y1, x2, y2, pen)
                arrow_size = 10
                direction = QPointF(x2 - x1, y2 - y1)
                length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
                if length == 0:
                    continue # Avoid division by zero for coincident nodes
                unit_direction = QPointF(direction.x() / length , direction.y() / length)
                arrow_point = QPointF(x2, y2) - unit_direction * arrow_size # Arrow points to node2
                perp = QPointF(-unit_direction.y() , unit_direction.x())
                p1 = arrow_point + perp * (arrow_size / 2) 
                p2 = arrow_point - perp * ( arrow_size / 2)
                arrow_head = QPolygonF([QPointF(x2,y2), p1 , p2])
                arrow_item = QGraphicsPolygonItem(arrow_head)
                arrow_item.setBrush(brush) # Use the determined brush
                self.scene.addItem(arrow_item)
            else:
                print(f"Warning: Skipping edge ({node1}-{node2}) due to missing node(s) during redraw.")

        for place_id, data in self.special_places.items():
            self.draw_special_place(QPointF(data['x'], data['y']), data['name'], place_id)

    def draw_special_place(self, pos, custom_name, place_id):
        # Marker for the special place (e.g., a red circle)
        marker_size = 12
        pen = QPen(QColor("red"))
        brush = QBrush(QColor(255, 0, 0, 128)) # Semi-transparent red
        ellipse = self.scene.addEllipse(pos.x() - marker_size / 2, pos.y() - marker_size / 2,
                                        marker_size, marker_size, pen, brush)
        ellipse.setToolTip(f"{custom_name} ({place_id})")

        # Text label for the special place
        text_item = QGraphicsTextItem(custom_name)
        text_item.setDefaultTextColor(QColor("darkred"))
        # Position text slightly below the marker
        text_item.setPos(pos.x() - text_item.boundingRect().width() / 2, pos.y() + marker_size / 2)
        self.scene.addItem(text_item)


    def undo(self):
        if not self.undo_stack:
            print("No actions to undo.")
            return

        action = self.undo_stack.pop()
        action_type = action[0]

        if action_type == "node_added": # Undoing a node addition
            node_name, _, _ = action
            if node_name in self.nodes:
                del self.nodes[node_name]
                self.cursor.execute("DELETE FROM nodes WHERE name = ?", (node_name,))
                # Also remove any edges connected to this node from self.edges and DB
                edges_to_remove = [edge for edge in self.edges if edge[0] == node_name or edge[1] == node_name]
                for edge in edges_to_remove:
                    self.edges.remove(edge)
                    self.cursor.execute("DELETE FROM edges WHERE (node_from = ? AND node_to = ?) OR (node_from = ? AND node_to = ?)",
                                        (edge[0], edge[1], edge[1], edge[0])) # Handles undirected if stored both ways, or directed
                self.conn.commit()
                self.redraw_graph()
                print(f"Node {node_name} addition undone.")

        elif action_type == "node_removed": # Undoing a node removal (restore node and its edges)
            node_name, x, y, restored_edges = action
            self.nodes[node_name] = (x, y)
            self.cursor.execute("INSERT INTO nodes (name, x, y) VALUES (?, ?, ?)", (node_name, x, y))
            for edge in restored_edges: # Restore edges that were connected to this node
                node1, node2 = edge
                # Recalculate weight or assume it was stored/not critical for this undo step
                # For simplicity, re-calculate if possible, or assume a default if not.
                # Here, we'll just add them back to self.edges and DB.
                # The original weight would be better if stored with the edge in undo.
                if node1 in self.nodes and node2 in self.nodes: # Check if both nodes for edge exist
                    weight = self.calculate_weight(node1, node2) # Recalculate weight
                    self.edges.append(edge)
                    self.cursor.execute("INSERT INTO edges (node_from, node_to, weight) VALUES (?, ?, ?)", (node1, node2, weight))
            self.conn.commit()
            self.redraw_graph()
            print(f"Node {node_name} restored.")
        
        elif action_type == "edge_added": # Undoing an edge addition
            node1, node2, weight = action # Weight is the one that was stored (normal or car_mode modified)
            edge_tuple = (node1, node2)
            reversed_edge_tuple = (node2, node1)

            if edge_tuple in self.edges:
                self.edges.remove(edge_tuple)
            elif reversed_edge_tuple in self.edges: # Handle if stored reversed
                self.edges.remove(reversed_edge_tuple)
                
            self.cursor.execute("DELETE FROM edges WHERE (node_from = ? AND node_to = ?) OR (node_from = ? AND node_to = ?)", 
                                (node1, node2, node2, node1))
            self.conn.commit()
            self.redraw_graph()
            print(f"Edge {node1} -> {node2} (Weight: {weight:.2f}) addition undone.")

        elif action_type == "remove_edge": # Undoing an edge removal (restore edge)
                                           # remove_edge appends ("remove_edge", edge)
            edge_to_restore, original_weight = action[1], action[2] # edge_to_restore is (n1, n2)
            node1, node2 = edge_to_restore
            if node1 in self.nodes and node2 in self.nodes: 
                self.edges.append(edge_to_restore) # Add (n1,n2) to self.edges
                self.cursor.execute("INSERT INTO edges (node_from, node_to, weight) VALUES (?, ?, ?)", 
                                    (node1, node2, original_weight))
                self.conn.commit()
                self.redraw_graph()
                print(f"Edge {node1} -> {node2} (Weight: {original_weight:.2f}) restored.")
        
        elif action_type == "special_place_added": # Undoing a special place addition
            place_id, _, _, _ = action 
            if place_id in self.special_places:
                del self.special_places[place_id]
                self.cursor.execute("DELETE FROM special_places WHERE id = ?", (place_id,))
                self.conn.commit()
                self.redraw_graph()
                print(f"Addition of special place {place_id} undone.")
        
        elif action_type == "special_place_removed":
            place_id, place_data = action
            self.special_places[place_id] = place_data
            self.cursor.execute("INSERT INTO special_places (id, custom_name, x, y) VALUES (?, ?, ?, ?)",
                                (place_id, place_data['name'], place_data['x'], place_data['y']))
            self.conn.commit()
            self.redraw_graph()
            print(f"Removal of special place {place_data.get('name', place_id)} undone.")
        else:
            print(f"Unknown action type in undo stack: {action_type}")
            self.undo_stack.append(action) # Put it back if not handled


    def keyPressEvent(self,event):
        if event.key() == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier: # Ctrl+Z for undo
            self.undo()
        elif event.key() == Qt.Key.Key_P: 
            self.toggle_special_place_mode()
            return 
        elif event.key() == Qt.Key.Key_C: # Toggle car mode
            self.toggle_car_mode()
            return # Event handled

        move_step = 75
        if event.key() == Qt.Key.Key_Left:
             self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - move_step)
        elif event.key() == Qt.Key.Key_Right:
             self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + move_step)
        elif event.key() == Qt.Key.Key_Up:
             self.verticalScrollBar().setValue(self.verticalScrollBar().value() - move_step)
        elif event.key() == Qt.Key.Key_Down:
             self.verticalScrollBar().setValue(self.verticalScrollBar().value() + move_step)
    def closeEvent(self, event):
        self.conn.close()
        event.accept()

    def get_node_position_from_db(self, node_name):
        self.cursor.execute("SELECT x, y FROM nodes WHERE name = ?", (node_name,))
        result = self.cursor.fetchone()
        return result[0], result[1] if result else (0, 0)


class Sidebar(QWidget):
    def __init__(self, graph_editor_instance, parent=None):
        super().__init__(parent)
        self.graph_editor = graph_editor_instance
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.special_place_button = QPushButton("Enable Special Place Mode")
        self.special_place_button.setCheckable(True)
        self.special_place_button.toggled.connect(self.on_special_place_toggled)
        layout.addWidget(self.special_place_button)

        self.car_mode_button = QPushButton("Enable Car Mode")
        self.car_mode_button.setCheckable(True)
        self.car_mode_button.toggled.connect(self.on_car_mode_toggled)
        layout.addWidget(self.car_mode_button)

        layout.addStretch() 

    def on_special_place_toggled(self, checked):
        self.graph_editor.set_special_place_mode(checked)

    def update_button_state(self, is_mode_active): # For special place mode
        self.special_place_button.setChecked(is_mode_active)
        if is_mode_active:
            self.special_place_button.setText("Disable Special Place Mode")
        else:
            self.special_place_button.setText("Enable Special Place Mode")

    def on_car_mode_toggled(self, checked):
        self.graph_editor.set_car_mode(checked)

    def update_car_mode_button_state(self, is_mode_active):
        self.car_mode_button.setChecked(is_mode_active)
        if is_mode_active:
            self.car_mode_button.setText("Disable Car Mode")
        else:
            self.car_mode_button.setText("Enable Car Mode")


class MainWindow(QMainWindow):
    def __init__(self, image_path, db_path="graph.db"):
        super().__init__()
        self.setWindowTitle("Graph Editor")
        self.setGeometry(100, 100, 1200, 800)

        self.graph_editor = GraphEditor(image_path, db_path)
        self.sidebar = Sidebar(self.graph_editor)
        
        self.graph_editor.sidebar_updater = self.sidebar.update_button_state
        self.graph_editor.car_mode_button_updater = self.sidebar.update_car_mode_button_state


        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        
        main_layout.addWidget(self.sidebar, 1) 
        main_layout.addWidget(self.graph_editor, 5) 

        self.setCentralWidget(central_widget)

    def closeEvent(self, event):
        self.graph_editor.closeEvent(event) # Ensure DB connection is closed
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow("map.png")
    main_window.show()
    sys.exit(app.exec())

