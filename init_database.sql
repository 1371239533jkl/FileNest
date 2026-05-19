-- =====================================================
-- 智能文件管家 - 数据库初始化脚本
-- 数据库: smart_file_manager
-- =====================================================

CREATE DATABASE IF NOT EXISTS smart_file_manager
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_file_manager;

-- 1. 文件索引表
CREATE TABLE IF NOT EXISTS files (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    file_path       VARCHAR(512)    NOT NULL        COMMENT '文件完整路径',
    file_name       VARCHAR(255)    NOT NULL        COMMENT '文件名',
    original_name   VARCHAR(255)    NULL            COMMENT '重命名前原始名',
    file_extension  VARCHAR(20)     NOT NULL        COMMENT '文件扩展名',
    file_type       VARCHAR(50)     NOT NULL        COMMENT '文件类型 image/document/video/audio/archive/other',
    file_size       BIGINT          NOT NULL        COMMENT '文件大小(字节)',
    file_hash       CHAR(64)        NULL            COMMENT 'SHA256哈希值',
    create_time     DATETIME        NULL            COMMENT '文件创建时间',
    modify_time     DATETIME        NULL            COMMENT '文件修改时间',
    scan_time       DATETIME        NOT NULL        COMMENT '扫描入库时间',
    is_duplicate    TINYINT         DEFAULT 0       COMMENT '是否重复文件 0否 1是',
    duplicate_group_id BIGINT       NULL            COMMENT '重复文件组ID',
    status          VARCHAR(20)     DEFAULT 'active' COMMENT '状态 active/deleted/moved',
    INDEX idx_file_path (file_path),
    INDEX idx_file_name (file_name),
    INDEX idx_file_extension (file_extension),
    INDEX idx_file_type (file_type),
    INDEX idx_file_hash (file_hash),
    INDEX idx_duplicate_group (duplicate_group_id),
    INDEX idx_scan_time (scan_time),
    INDEX idx_type_time (file_type, modify_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件索引表';

-- 2. 文件元数据表
CREATE TABLE IF NOT EXISTS file_metadata (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    file_id         BIGINT          NOT NULL        COMMENT '关联文件ID',
    width           INT             NULL            COMMENT '图片宽度',
    height          INT             NULL            COMMENT '图片高度',
    photo_taken_time DATETIME       NULL            COMMENT 'EXIF拍摄时间',
    camera_model    VARCHAR(100)    NULL            COMMENT '相机型号',
    gps_latitude    DECIMAL(10,8)   NULL            COMMENT 'GPS纬度',
    gps_longitude   DECIMAL(11,8)   NULL            COMMENT 'GPS经度',
    pdf_title       VARCHAR(255)    NULL            COMMENT 'PDF标题',
    pdf_author      VARCHAR(100)    NULL            COMMENT 'PDF作者',
    pdf_pages       INT             NULL            COMMENT 'PDF页数',
    video_duration  INT             NULL            COMMENT '视频时长(秒)',
    video_resolution VARCHAR(20)    NULL            COMMENT '视频分辨率',
    extra_data      TEXT            NULL            COMMENT '其他元数据(JSON)',
    UNIQUE INDEX idx_file_id (file_id),
    CONSTRAINT fk_metadata_file FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件元数据表';

-- 3. 文件分类记录表
CREATE TABLE IF NOT EXISTS file_classifications (
    id                  BIGINT      AUTO_INCREMENT PRIMARY KEY,
    file_id             BIGINT      NOT NULL        COMMENT '关联文件ID',
    classification_type VARCHAR(50) NOT NULL        COMMENT '分类类型 by_type/by_date/by_keyword/manual',
    classification_value VARCHAR(255) NOT NULL      COMMENT '分类值',
    classification_time DATETIME    NOT NULL        COMMENT '分类时间',
    confidence_score    DECIMAL(3,2) DEFAULT 1.00   COMMENT '置信度 0.00-1.00',
    INDEX idx_file_class (file_id, classification_type),
    CONSTRAINT fk_class_file FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件分类记录表';

-- 4. 操作历史表
CREATE TABLE IF NOT EXISTS operation_history (
    id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
    operation_type  VARCHAR(50)     NOT NULL        COMMENT '操作类型 scan/rename/move/classify/dedup/delete/restore',
    operation_time  DATETIME        NOT NULL        COMMENT '操作时间',
    file_id         BIGINT          NULL            COMMENT '关联文件ID',
    old_value       VARCHAR(512)    NULL            COMMENT '旧值(路径/文件名等)',
    new_value       VARCHAR(512)    NULL            COMMENT '新值',
    operation_status VARCHAR(20)    DEFAULT 'completed' COMMENT '状态 completed/failed/undone',
    undo_available  TINYINT         DEFAULT 1       COMMENT '是否可撤销',
    error_message   TEXT            NULL            COMMENT '错误信息',
    batch_id        VARCHAR(64)     NULL            COMMENT '批次ID',
    INDEX idx_time (operation_time DESC),
    INDEX idx_batch (batch_id),
    INDEX idx_file_id (file_id),
    INDEX idx_status (operation_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作历史表';

-- 5. 扫描目录配置表
CREATE TABLE IF NOT EXISTS scan_directories (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    directory_path  VARCHAR(512)    NOT NULL        COMMENT '目录路径',
    is_active       TINYINT         DEFAULT 1       COMMENT '是否启用',
    scan_recursive  TINYINT         DEFAULT 1       COMMENT '是否递归扫描',
    last_scan_time  DATETIME        NULL            COMMENT '最后扫描时间',
    file_count      INT             DEFAULT 0       COMMENT '文件数量',
    create_time     DATETIME        NOT NULL        COMMENT '创建时间',
    UNIQUE INDEX idx_dir_path (directory_path)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='扫描目录配置表';

-- 6. 分类规则表
CREATE TABLE IF NOT EXISTS classification_rules (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    rule_name       VARCHAR(100)    NOT NULL        COMMENT '规则名称',
    rule_type       VARCHAR(50)     NOT NULL        COMMENT '规则类型 keyword/extension/metadata',
    rule_pattern    VARCHAR(255)    NOT NULL        COMMENT '规则模式(关键词/正则)',
    target_category VARCHAR(100)    NOT NULL        COMMENT '目标分类',
    priority        INT             DEFAULT 0       COMMENT '优先级(越大越高)',
    is_enabled      TINYINT         DEFAULT 1       COMMENT '是否启用',
    create_time     DATETIME        NOT NULL        COMMENT '创建时间',
    INDEX idx_priority (priority DESC),
    INDEX idx_enabled (is_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分类规则表';

-- 7. 系统设置表
CREATE TABLE IF NOT EXISTS system_settings (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    setting_key     VARCHAR(100)    NOT NULL        COMMENT '设置键',
    setting_value   TEXT            NOT NULL        COMMENT '设置值',
    setting_type    VARCHAR(20)     DEFAULT 'string' COMMENT '值类型 string/int/bool/json',
    description     VARCHAR(255)    NULL            COMMENT '描述',
    update_time     DATETIME        NULL            COMMENT '更新时间',
    UNIQUE INDEX idx_key (setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统设置表';

-- 8. 文件标签表
CREATE TABLE IF NOT EXISTS file_tags (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    file_id         BIGINT          NOT NULL        COMMENT '关联文件ID',
    tag_name        VARCHAR(100)    NOT NULL        COMMENT '标签名称',
    create_time     DATETIME        NOT NULL        COMMENT '创建时间',
    UNIQUE INDEX idx_file_tag (file_id, tag_name),
    INDEX idx_tag_name (tag_name),
    CONSTRAINT fk_tag_file FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件标签表';

-- 插入默认设置（IGNORE 避免重复初始化报错）
INSERT IGNORE INTO system_settings (setting_key, setting_value, setting_type, description, update_time) VALUES
('rename_pattern', '{date}_{type}_{original_name}', 'string', '默认重命名模板', NOW()),
('dedup_strategy', 'keep_newest', 'string', '默认去重策略', NOW()),
('hash_algorithm', 'sha256', 'string', '哈希算法', NOW()),
('scan_recursive', '1', 'bool', '默认递归扫描', NOW()),
('include_hidden', '0', 'bool', '包含隐藏文件', NOW()),
('max_hash_size_mb', '500', 'int', '计算哈希的最大文件大小(MB)', NOW());

-- 插入默认分类规则（IGNORE 避免重复初始化报错）
INSERT IGNORE INTO classification_rules (rule_name, rule_type, rule_pattern, target_category, priority, is_enabled, create_time) VALUES
('工作文件', 'keyword', '报告|会议|方案|合同|发票|report|meeting|invoice', '工作', 10, 1, NOW()),
('学习资料', 'keyword', '笔记|课件|作业|论文|note|homework|thesis', '学习', 10, 1, NOW()),
('生活照片', 'keyword', '照片|旅游|美食|photo|travel|food', '生活', 10, 1, NOW()),
('项目文件', 'keyword', '代码|设计|需求|测试|code|design|test', '项目', 10, 1, NOW());

-- 13. 独立标签表（可存在不关联任何文件的标签）
CREATE TABLE IF NOT EXISTS tags (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    tag_name        VARCHAR(100)    NOT NULL        COMMENT '标签名称',
    create_time     DATETIME        NOT NULL        COMMENT '创建时间',
    UNIQUE INDEX idx_tag_name (tag_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='独立标签表';
