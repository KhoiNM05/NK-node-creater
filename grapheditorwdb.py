import sys
import sqlite3
from PyQt6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsPolygonItem
from PyQt6.QtGui import QPixmap, QPen, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QPointF
import uuid  # Import thêm thư viện uuid

class GraphEditor(QGraphicsView):
    def __init__(self, image_path, db_path="graph.db"):
        super().__init__()
        self.is_panning = False
        self.last_pan_point = None
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
        self.edges = []
        self.is_panning = False
        self.last_pan_point = None
        self.selected_nodes = [] 
        self.load_graph()
    
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
        self.conn.commit()
    def remove_edge(self, edge):
        if edge not in self.edges:
            return
        self.undo_stack.append(("remove_edge", edge))
        self.edges.remove(edge)
        self.cursor.execute("DELETE FROM edges WHERE node_from = ? AND node_to = ?", (edge[0], edge[1]))
        self.conn.commit()
        print(f"Edge removed: {edge[0]} -> {edge[1]}")
        self.redraw_graph() 
    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            self.cursor.execute("SELECT COUNT(*) FROM nodes WHERE x = ? and y = ?", (pos.x(), pos.y()))
            exists = self.cursor.fetchone()[0]
            if exists:
                print("The nodes already exists")
            node_name = f"N{uuid.uuid4().hex[:6]}"
            self.nodes[node_name] = (pos.x(), pos.y())
            self.undo_stack.append(("node", node_name))
            self.cursor.execute("INSERT INTO nodes (name, x, y) VALUES (?, ?, ?)", (node_name, pos.x(), pos.y()))
            self.conn.commit()
            self.draw_node(pos, node_name)
            print(f"Node added: {node_name} at {pos.x()}, {pos.y()}")
        elif event.button() == Qt.MouseButton.RightButton:
            clicked_edge = self.find_clicked_edge(pos)
            if clicked_edge:
                if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                    self.remove_edge(clicked_edge)
            else:

                closest_node = self.find_closest_node(pos)
                if closest_node:
                    if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                        self.remove_node(closest_node)
                    else:
                        self.selected_nodes.append(closest_node)
                        print(f"Selected node: {closest_node}")
                        if len(self.selected_nodes) == 2:
                            self.create_edge(self.selected_nodes[0], self.selected_nodes[1])
                            self.selected_nodes.clear()
        elif QApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier and event.button() == Qt.MouseButton.LeftButton:
            self.is_spanning = True
            self.last_pan_point = event.position()
            self.setCursor(Qt.Cursor.ClosedHandCursor)
        else:
            super().mousePressEvent(event)
    
    def remove_node(self, node_name):
        if node_name not in self.nodes:
            return

        # Tìm tất cả các cạnh liên quan đến node này
        related_edges = [(n1, n2) for n1, n2 in self.edges if n1 == node_name or n2 == node_name]
        self.undo_stack.append(("node", "remove", node_name))

        # Xóa node khỏi database
        self.cursor.execute("DELETE FROM nodes WHERE name = ?", (node_name,))
        self.cursor.execute("DELETE FROM edges WHERE node_from = ? OR node_to = ?", (node_name, node_name))
        self.conn.commit()

        # Lưu vào undo stack

        # Xóa node và các cạnh liên quan khỏi bộ nhớ
        del self.nodes[node_name]
        for edge in related_edges:
            self.edges.remove(edge)

        print(f"Node {node_name} removed.")
        self.redraw_graph()

        
    def draw_node(self, pos, label):
        pen = QPen(Qt.GlobalColor.black)
        brush = QBrush(Qt.GlobalColor.green)
        self.scene.addEllipse(pos.x() - 5, pos.y() - 5, 10, 10, pen, brush)
    
    def create_edge(self, node1, node2):
        if any(e == (node1, node2) for e in self.edges):
            return
        x1, y1 = self.nodes[node1]
        x2, y2 = self.nodes[node2]
        pen = QPen(Qt.GlobalColor.blue, 2)
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
        arrow_item.setBrush(QBrush(Qt.GlobalColor.blue))
        self.scene.addItem(arrow_item)
        self.edges.append((node1, node2))
        self.cursor.execute("INSERT INTO edges (node_from, node_to, weight) VALUES (?, ?, ?)", (node1, node2, self.calculate_weight(node1, node2)))
        self.conn.commit()
        self.undo_stack.append(("edge", node1, node2))
    def calculate_weight(self,node1, node2):
        x1, y1 = self.nodes[node1]
        x2, y2 = self.nodes[node2]
        return round(((x2-x1) ** 2 + (y2- y1)**2) ** 0.5 /100, 4)
    def find_closest_node(self, pos):
        min_dist = float('inf')
        closest_node = None
        for node, (x, y) in self.nodes.items():
            dist = (pos.x() - x) ** 2 + (pos.y() - y) ** 2
            if dist < min_dist:
                min_dist = dist
                closest_node = node
        return closest_node
    def find_clicked_edge(self, pos):
        click_tolerance = 2  # Giảm sai số cho phép khi click cạnh

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
        self.cursor.execute("SELECT * FROM edges")
        self.edges = [(row[0], row[1]) for row in self.cursor.fetchall()]
        self.redraw_graph()
    
    def redraw_graph(self):
        self.scene.clear()
        self.scene.addItem(QGraphicsPixmapItem(QPixmap(self.image_path)))
        for node, (x, y) in self.nodes.items():
            self.draw_node(QPointF(x, y), node)
        for node1, node2 in self.edges:
            x1, y1 = self.nodes[node1]
            x2, y2 = self.nodes[node2]
            pen = QPen(Qt.GlobalColor.blue, 2)
            self.scene.addLine(x1, y1, x2, y2, pen)
            arrow_size = 10
            direction = QPointF(x2 - x1, y2 - y1)
            length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
            if length == 0:
                return
            unit_direction = QPointF(direction.x() / length , direction.y() / length)
            arrow_point = QPointF(x2, y2) - unit_direction * arrow_size
            perp = QPointF(-unit_direction.y() , unit_direction.x())
            p1 = arrow_point + perp * (arrow_size / 2) 
            p2 = arrow_point - perp * ( arrow_size / 2)
            arrow_head = QPolygonF([QPointF(x2,y2), p1 , p2])
            arrow_item = QGraphicsPolygonItem(arrow_head)
            arrow_item.setBrush(QBrush(Qt.GlobalColor.blue))
            self.scene.addItem(arrow_item)

    def undo(self):
        if not self.undo_stack:
            print("No actions to undo.")
            return

        # Lấy hành động cuối cùng từ undo_stack
        action = self.undo_stack.pop()

        if action[0] == "node":
            if action[1] == "remove":
                # Phục hồi node đã bị xóa
                node_name = action[2]
                self.nodes[node_name] = self.get_node_position_from_db(node_name)
                self.redraw_graph()
                print(f"Node {node_name} restored.")

        elif action[0] == "edge":
            if action[1] == "remove":
                # Phục hồi cạnh đã bị xóa
                node1, node2 = action[2], action[3]
                self.edges.append((node1, node2))
                self.cursor.execute("INSERT INTO edges (node_from, node_to, weight) VALUES (?, ?, ?)", (node1, node2, self.calculate_weight(node1, node2)))
                self.conn.commit()
                self.redraw_graph()
                print(f"Edge {node1} -> {node2} restored.")
            
            elif action[1] == "create":
                # Xóa cạnh đã được tạo
                node1, node2 = action[2], action[3]
                self.edges.remove((node1, node2))
                self.cursor.execute("DELETE FROM edges WHERE node_from = ? AND node_to = ?", (node1, node2))
                self.conn.commit()
                self.redraw_graph()
                print(f"Edge {node1} -> {node2} removed.")

    def keyPressEvent(self,event):
        if event.key() == Qt.Key.Key_Z:
            self.undo()
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = GraphEditor("map.png")
    editor.show()
    sys.exit(app.exec())

