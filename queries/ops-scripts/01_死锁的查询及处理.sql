-- ===================================================================
-- 01 死锁（锁阻塞）的查询及处理
-- 说明：Oracle 会自动检测并解除真正的死锁（报 ORA-00060 并回滚其中一个会话），
--       因此本脚本实际排查的是“锁等待/阻塞”问题，需人工介入处理
-- ===================================================================

-- 查询持有/等待锁的会话
-- LOCKWAIT 不为空表示该会话正在等待锁（被其他会话阻塞）
-- BLOCKING_SESSION 即为阻塞它的会话，终止时优先处理阻塞源头
SELECT S.USERNAME,
       S.LOCKWAIT,
       S.BLOCKING_SESSION,
       S.STATUS,
       S.MACHINE,
       S.PROGRAM
  FROM V$SESSION S
 WHERE S.SID IN (SELECT LO.SESSION_ID
                   FROM V$LOCKED_OBJECT LO);

-- 查询上述会话当前正在执行的 SQL 语句
-- 会话空闲时 SQL_HASH_VALUE 为 0，查不到结果
SELECT SQ.SQL_TEXT
  FROM V$SQL SQ
 WHERE SQ.HASH_VALUE IN (SELECT S.SQL_HASH_VALUE
                           FROM V$SESSION S
                          WHERE S.SID IN (SELECT LO.SESSION_ID
                                            FROM V$LOCKED_OBJECT LO));

-- 查找持有/等待锁的会话进程信息
SELECT S.USERNAME,
       LO.OBJECT_ID,
       LO.SESSION_ID,
       S.SERIAL#,
       LO.ORACLE_USERNAME,
       LO.OS_USER_NAME,
       LO.PROCESS
  FROM V$LOCKED_OBJECT LO,
       V$SESSION S
 WHERE LO.SESSION_ID = S.SID;

-- 终止阻塞会话（sid = LO.SESSION_ID；serial# = S.SERIAL#，取自上一查询）
-- 注意：先确认是阻塞源头再终止；普通 KILL 后会话标记为 KILLED，需等待其回滚完成，
--       紧急情况可改用 IMMEDIATE
ALTER SYSTEM KILL SESSION 'sid,serial#';
ALTER SYSTEM KILL SESSION '1062,4935'; -- 示例：sid=1062，serial#=4935
