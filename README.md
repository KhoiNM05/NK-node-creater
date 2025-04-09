# Hướng dẫn sử dụng
- Cài sqlite 
    + Với Ubuntu-based

    ```
    sudo apt install sqlite
    ```
    + Với Fedora

    ``` 
    sudo dnf install sqlite
    ```
- Đầu tiên cài PyQT6 bằng cách dùng lệnh:

```
pip install PyQT6 
```
- Sau đấy thì chạy file `grapheditorwdb.py` bằng `python grapeditorwdb.py` (lưu ý đặt `map.png` với `grapheditorwdb.py` trong cùng 1 foler  )


## Phím tắt:

- Chuột trái tạo node (tạo node cần phải đặt tại các điểm giao, các điểm gấp khúc , nên đặt node gần nhau một chút  để sau này sẽ phải dùng một số features như tìm đường, thêm yếu tố tắc đường các thứ)
- Để vẽ cạnh thì:
    + Chuột phải vào vào điểm đầu , sau đó là điểm cuối thì nó sẽ tự vẽ ra cạnh (1 chiều) (2 chiều thì phải vẽ thêm cạnh ngược lại) (để ý ký hiệu đường 1 chiều trên map, cũng như đoạn nào bắt buộc rẽ trái rẽ phải để nhập làn chẳng hạn)
- Muốn xóa thì Shift + Chuột phải vào node hoặc cạnh
- Dùng arrow keys để di chuyển quanh map
- Lăn chuột để zoom

> !Note
- Bắt buộc tại các nút ngã ba, ngã tư , nút rẽ phải có node. 
- Làm xong bấm S để save, đừng có xóa file graph.json đi vì nó là output để làm tiếp
- Nếu thấy đơ có thể save lại rồi chạy lại chương trình
