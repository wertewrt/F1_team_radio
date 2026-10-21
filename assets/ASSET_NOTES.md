# 素材与高清字形说明

## 渲染方式

号码使用 numerals/contours.json 中经过直边、平行线与折角校正的矢量多边形，在目标分辨率直接渲染。数字6以原图里的短顶帽、长斜线和八角下腹为结构参考，所有车手共用同一套0–9轮廓；9在源图中没有出现，以6旋转180°作为一致风格扩展。

姓名与 RADIO 使用 fonts/RadioRounded-Bold.ttf 和 fonts/RadioRounded-Radio.ttf 的独立圆润矢量轮廓。它们与硬边号码不同，不使用低分辨率文字贴图放大。源图中的整段文字和灰度字母只作为字形/字宽/位置的测量与审核材料，保存在 lettering 中。

这套字形是依据参考图重建的清晰字形，并非取得了官方原版专有字体。源图像素模糊、压缩和偏色不能唯一决定原始字体的所有精确曲率，重建时优先恢复直线、明确折角以及平滑圆润曲线。ALBON 以同一圆润字库排版，号码23来自统一矢量数字。中文与扩展字符没有参考图字形，使用本机微软雅黑或 DejaVu 回退。DejaVu 许可见 fonts/LICENSE_DEJAVU.txt。

## 图片素材

logos 中的车队彩色、白色两版徽标，从用户提供的 resource/team_catalog.png 分离；保留各自标识配色。徽标源图约150px宽，高清放大受源素材限制，可上传更清晰的透明 PNG/WebP 队标替换。队标属于各自权利人。

background/reference_panel.png 的斜纹来自源图可见区域；原文字、号码与波形区域被遮罩后补全。顶缘按当前统一强调色施加浅色光。原图完全被文字遮挡的底纹只能推测，不声称恢复未知原始工程。

## 开发工具

tools/extract_numerals.py 与 tools/extract_lettering.py 保留可重复的原图测量及提取过程；tools/build_rounded_font.py 生成可直接渲染的 TrueType 曲线字体。开发时重建字体需要 fonttools、opencv-python 等额外库，日常运行不需要这些开发依赖。

原 resource 文件不被修改。
