-- =============================================================
-- HR 人力池系统 · 初始数据（种子）V1.0
-- 数据库：MySQL 5.7.32+ / 8.x
--
-- 用法：先建表，再执行本文件
--   mysql -u root -p < database/schema.sql
--   mysql -u root -p < database/seed.sql
--
-- 本文件可重复执行（WHERE NOT EXISTS 保证幂等）
-- =============================================================

USE hr_system;

-- -------------------------------------------------------------
-- 初始管理员账号（参赛演示版专用，密码已随机化，与生产无关）
-- password_hash 为 bcrypt 哈希，密码由参赛者单独保管
--
-- ⚠️ 上线前必须修改密码！修改方式：
--   1) 登录管理后台后在「员工管理」里重置，或
--   2) 生成新哈希后直接 UPDATE：
--      INSERT ... 或
--      UPDATE staff SET password_hash='<新哈希>' WHERE username='admin';
-- =============================================================
INSERT INTO staff (username, password_hash, real_name, role, status)
SELECT 'admin',
       '$2b$12$hchDBEYBJLTFlZOIgispqeqitq.ZpFp1v5s9hV92M/HthoXPntyNm',
       '系统管理员',
       'admin',
       'active'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM staff WHERE username = 'admin');
