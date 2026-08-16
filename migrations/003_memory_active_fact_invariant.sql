-- 一个 merchant 的同一 subject/predicate 在任意时刻只有一个当前事实。
-- 写入路径在 materialize_fact 中先取得同一语义键的事务 advisory lock；该
-- 部分唯一索引作为崩溃恢复、脚本误用和未来调用方的数据库级最终防线。
CREATE UNIQUE INDEX IF NOT EXISTS memory_facts_one_active_semantic_key
    ON memory_facts (merchant_id, subject, predicate)
 WHERE status = 'active' AND valid_to IS NULL;
