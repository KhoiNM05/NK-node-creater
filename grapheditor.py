import sys
from PyQt6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsPolygonItem
import json
from PyQt6.QtGui import QPixmap, QPen, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QTransform
class GraphEditor(QGraphicsView):
    def __init__(self, image_path, json_path="graph.json"):
        super().__init__()
        self.is_panning = False
        self.last_pan_point = None
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.undo_stack = []
        self.image_path = image_path
        # Load bản đồ
        pixmap = QPixmap(image_path)
        self.map_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.map_item)
        self.zoom_factor = 1.0
        self.max_zoom = 3.0  # Giới hạn zoom tối đa
        self.min_zoom = 0.5

        # Danh sách nodes và edges
        self.nodes = {}
        self.edges = []
        self.selected_nodes = []
        self.json_path = json_path

        self.load_graph()
    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            # Thêm node mới
            node_name = f"N{len(self.nodes)}"
            self.nodes[node_name] = {"pos": (pos.x(), pos.y()), "attributes": {}}
            self.undo_stack.append(("node", node_name))
            self.draw_node(pos, node_name)
            print(f"Node added: {node_name} at {pos.x()}, {pos.y()}")
        elif event.button() == Qt.MouseButton.RightButton:
            # Kiểm tra nếu click vào cạnh
            clicked_edge = self.find_clicked_edge(pos)
            if clicked_edge:
                self.remove_edge(clicked_edge)
            else:
                 # Nếu không, chọn node để tạo cạnh
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
        elif  QApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier and event.button() == Qt.MouseButton.LeftButton:
            self.is_panning = True
            self.last_pan_point = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)
    def remove_node(self, node_name):
        if node_name not in self.nodes:
            print(f"Node {node_name} does not exist!")
            return

    # Xóa tất cả các cạnh liên quan đến nút này
        self.edges = [e for e in self.edges if e["from"] != node_name and e["to"] != node_name]

    # Xóa nút khỏi danh sách
        del self.nodes[node_name]
        self.undo_stack.append(("remove_node", node_name))

        print(f"Node {node_name} removed.")
        self.redraw_graph()
    def mouseMoveEvent(self, event):
        if self.is_panning and self.last_pan_point:
            delta = event.position() - self.last_pan_point
            self.last_pan_point = event.position()
            self.setSceneRect(self.sceneRect().translated(-delta.x(), -delta.y()))
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if self.is_panning and event.button() == Qt.MouseButton.LeftButton:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)
    def find_clicked_edge(self, pos):
        click_torelance = 5
        for edge in self.edges:
            x1, y1 = self.nodes[edge["from"]]["pos"]
            x2, y2 = self.nodes[edge["to"]]["pos"]
            if x2 - x1 != 0:
                m = (y2 - y1) / (x2-x1)
                exp_y = m * (pos.x() - x1) + y1
            else:
                exp_y = y1
            if abs(pos.y() - exp_y) < click_torelance and min(x1, x2) <= pos.x() <= max(x1, x2):
                print(f"Clicked on edge: {edge['from']} -> {edge["to"]}")
                return edge
        return None
    def remove_edge(self, edge):
        self.edges.remove(edge)
        self.undo_stack.append(("remove_edge", edge))
        print(f"Edge removed: {edge['from']} -> {edge['to']}")
        self.redraw_graph()
    def draw_node(self, pos, label):
        pen = QPen(Qt.GlobalColor.black)
        brush = QBrush(Qt.GlobalColor.green)
        self.scene.addEllipse(pos.x() - 5, pos.y() - 5, 10, 10, pen, brush)
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
    def create_edge(self, node1, node2):
        if any(e["from"] == node1  and e["to"] == node2 for e in self.edges ):
            print(f"Edge {node1} -> {node2} already exists. Skipping")
            return
        x1, y1 = self.nodes[node1]["pos"]
        x2, y2 = self.nodes[node2]["pos"]
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
        self.edges.append({"from": node1, "to": node2, "weight": self.calculate_weight(node1, node2)})
        self.undo_stack.append(("edge", node1, node2))
        print(f"Edge created: {node1} -> {node2}")
    def draw_edge_with_arrow(self, node1, node2):
         x2, y2 = self.nodes[node2]["pos"]
         x1, y1 = self.nodes[node1]["pos"]
         
         pen = QPen(Qt.GlobalColor.blue, 2)
         
         # Draw the main edge line
         self.scene.addLine(x1, y1, x2, y2, pen)

         # Calculate arrowhead direction
         arrow_size = 10
         dx, dy = x2 - x1, y2 - y1
         length = (dx**2 + dy**2) ** 0.5
         if length == 0:
             return  # Avoid division by zero

         dx /= length
         dy /= length

         # Calculate arrowhead points
         arrow_p1 = QPointF(x2 - arrow_size * (dx - dy), y2 - arrow_size * (dy + dx))
         arrow_p2 = QPointF(x2 - arrow_size * (dx + dy), y2 - arrow_size * (dy - dx))

         # Draw arrowhead
         self.scene.addLine(x2, y2, arrow_p1.x(), arrow_p1.y(), pen)
         self.scene.addLine(x2, y2, arrow_p2.x(), arrow_p2.y(), pen)

         print(f"Edge drawn: {node1} -> {node2} with arrow")

    def calculate_weight(self, node1, node2):
        x1, y1 = self.nodes[node1]["pos"]
        x2, y2 = self.nodes[node2]["pos"]
        return round(((x2 - x1)**2 + (y2 - y1)**2) ** 0.5 / 10, 2)  # Scale khoảng cách

    def find_closest_node(self, pos):
        min_dist = float('inf')
        closest_node = None
        for node, data in self.nodes.items():
            x, y = data["pos"]
            dist = (pos.x() - x) ** 2 + (pos.y() - y) ** 2
            if dist < min_dist:
                min_dist = dist
                closest_node = node
        return closest_node

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_S:
            self.save_graph()
        move_step = 75  # Dịch chuyển 50 pixel mỗi lần nhấn phím

        if event.key() == Qt.Key.Key_Left:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - move_step)
        elif event.key() == Qt.Key.Key_Right:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + move_step)
        elif event.key() == Qt.Key.Key_Up:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - move_step)
        elif event.key() == Qt.Key.Key_Down:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + move_step)
        elif event.key() == Qt.Key.Key_Z:
            self.undo()  # Hoàn tác
    def undo(self):

        if not self.undo_stack:
            print("Nothing to undo.")
            return
        action = self.undo_stack.pop()
        if action[0] == "node":
            self.redraw_graph()
            node_name = action[1]
            del self.nodes[node_name]
            print(f"Undo node: {node_name}")
        elif action[0] == "edge":
            node1, node2 = action[1], action[2]
            self.edges = [e for e in self.edges if not (e["from"] == node1 and e["to"] == node2)]
            print(f"Undo edge: {node1} -> {node2}")
        self.redraw_graph()
    def save_graph(self):
        data = {"nodes": self.nodes, "edges": self.edges}
        with open(self.json_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Graph saved to {self.json_path}")

    def load_graph(self):
        try:
            with open(self.json_path, "r") as f:
                data = json.load(f)
                self.nodes = data.get("nodes", {})
                self.edges = data.get("edges", [])

                print("Loaded nodes:", self.nodes)  # Debugging

            # Chuyển đổi danh sách thành dictionary với key "pos"
                for node, pos in self.nodes.items():
                    if isinstance(pos, list) and len(pos) == 2:
                        self.nodes[node] = {"pos": tuple(pos)}

                self.redraw_graph()
                print("Graph loaded from JSON")
        except FileNotFoundError:
            print("No existing graph file found. Starting fresh.")
    def redraw_graph(self):
        print("Redrawing graph...")
        self.scene.clear()
        self.map_item = QGraphicsPixmapItem(QPixmap(self.image_path))
        self.scene.addItem(self.map_item)
        # Vẽ lại các node
        for node, pos in self.nodes.items():
            try:
                print(f"Drawing node {node} at {pos}")
                x, y = self.nodes[node]["pos"]
                self.draw_node(QPointF(x, y), node)
            except:
                print("Pos",  node, "hehe", self.nodes[node]["pos"][0])
                print("Error")
        # Vẽ lại các cạnh
        for edge in self.edges:
            print(f"Drawing edge {edge['from']} -> {edge['to']}")
            self.draw_edge_with_arrow(edge["from"], edge["to"])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = GraphEditor("map.png")  # Đổi đường dẫn ảnh nếu cần
    editor.show()
    sys.exit(app.exec())

