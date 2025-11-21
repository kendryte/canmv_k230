#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"

void rgb888_compress(FrameSize frame_shape, uint8_t* data, int jpeg_quality, uint8_t* result)
{
    // 1. 封装为 Mat（输入是 RGB888）
    cv::Mat img_rgb(frame_shape.height, frame_shape.width, CV_8UC3, data);

    // 2. 转换为 OpenCV 期望的 BGR 顺序
    cv::Mat img_bgr;
    cv::cvtColor(img_rgb, img_bgr, cv::COLOR_RGB2BGR);

    // 3. 压缩参数
    int quality = jpeg_quality;
    if (quality < 1)  quality = 1;
    if (quality > 100) quality = 100;
    std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, quality};

    // 4. JPEG 压缩
    std::vector<uchar> jpeg_buf;
    cv::imencode(".jpg", img_bgr, jpeg_buf, params);

    // 5. 解码 JPEG 回 BGR
    cv::Mat decompressed = cv::imdecode(jpeg_buf, cv::IMREAD_COLOR);

    // 6. 再转回 RGB
    cv::cvtColor(decompressed, decompressed, cv::COLOR_BGR2RGB);

    // 7. 拷贝输出
    size_t data_size = decompressed.total() * decompressed.channels();
    std::memcpy(result, decompressed.data, data_size);
    
}
