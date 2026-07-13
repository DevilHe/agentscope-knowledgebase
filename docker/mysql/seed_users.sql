-- 预置登录账号（bcrypt 哈希；管理员密码见 .env 中 ADMIN_PASSWORD，重启 backend 同步）
-- 用法:
--   docker exec -i rag-mysql mysql -urag -prag123456 rag_standards < docker/mysql/seed_users.sql

INSERT INTO users (id, username, password_hash, role, created_at)
VALUES
  (
    'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaa01',
    'admin',
    '$2b$12$32XDaq3MJwG5JI7z03lNHehcKwu0BUBhlJD6mv5H.EgyWHRNBF212',
    'admin',
    NOW()
  ),
  (
    'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaa02',
    'user',
    '$2b$12$lgG1Hg.p.dSPSbt1UO3zQOcYPQX1QtznctON.XuMppQwpL/XQhNxu',
    'user',
    NOW()
  )
ON DUPLICATE KEY UPDATE
  password_hash = VALUES(password_hash),
  role = VALUES(role);
