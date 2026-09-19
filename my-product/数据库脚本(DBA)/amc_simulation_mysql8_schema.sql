-- ============================================================================
-- 诺迪达空气智慧平台 AMC-Simulation
-- MySQL 8.0 数据库初始化脚本
-- 版本: V1.0
-- 字符集: utf8mb4
-- 存储引擎: InnoDB
--
-- 设计依据:
--   1. AMC洁净室稳态模拟软件_数据库设计说明.docx
--   2. AMC洁净室稳态模拟软件_PRD_V1.0.docx
--   3. my-product/web1 当前前端数据结构
--
-- 说明:
--   - 保留数据库设计说明中的 13 张核心表。
--   - 增加 PRD 强制要求的 calc_input_snapshot、import_record、
--     export_record、system_config 4 张支撑表，共 17 张表。
--   - API 中的浓度单位 ug 应在服务层映射为数据库值 ugm3。
--   - 浓度展示列使用 DECIMAL(18,6)，未舍入值以 JSON 字符串快照保存。
-- ============================================================================

CREATE DATABASE IF NOT EXISTS amc_simulation
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE amc_simulation;

SET NAMES utf8mb4;
SET time_zone = '+08:00';

-- --------------------------------------------------------------------------
-- 1. 用户表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sys_user (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  username        VARCHAR(50)  NOT NULL COMMENT '登录名',
  password_hash   VARCHAR(100) NOT NULL COMMENT '强哈希后的密码，禁止存明文',
  real_name       VARCHAR(50)  NULL COMMENT '姓名',
  role            VARCHAR(20)  NOT NULL COMMENT 'admin/engineer/sales/manager/customer',
  data_scope      JSON         NULL COMMENT '数据范围授权快照',
  status          VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'active/disabled',
  last_login_at   DATETIME     NULL COMMENT '最后登录时间',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sys_user_username (username),
  KEY idx_sys_user_role_status (role, status),
  CONSTRAINT chk_sys_user_role CHECK (role IN ('admin', 'engineer', 'sales', 'manager', 'customer')),
  CONSTRAINT chk_sys_user_status CHECK (status IN ('active', 'disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统用户';

-- --------------------------------------------------------------------------
-- 2. 客户表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  name            VARCHAR(100) NOT NULL COMMENT '客户名称',
  contact         VARCHAR(50)  NULL COMMENT '联系人',
  phone           VARCHAR(30)  NULL COMMENT '联系电话',
  remark          VARCHAR(255) NULL COMMENT '备注',
  status          VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'active/deleted，逻辑删除',
  created_by      BIGINT       NOT NULL COMMENT '创建人',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_customer_name_status (name, status),
  KEY idx_customer_created_by (created_by),
  CONSTRAINT fk_customer_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_customer_status CHECK (status IN ('active', 'deleted'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户档案';

-- --------------------------------------------------------------------------
-- 3. 项目表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  customer_id     BIGINT       NOT NULL COMMENT '所属客户',
  name            VARCHAR(100) NOT NULL COMMENT '项目名称',
  location        VARCHAR(150) NULL COMMENT '现场位置',
  remark          VARCHAR(255) NULL COMMENT '备注',
  status          VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'active/deleted，逻辑删除',
  created_by      BIGINT       NOT NULL COMMENT '创建人',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_project_customer_status (customer_id, status),
  KEY idx_project_name (name),
  KEY idx_project_created_by (created_by),
  CONSTRAINT fk_project_customer FOREIGN KEY (customer_id) REFERENCES customer (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_project_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_project_status CHECK (status IN ('active', 'deleted'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客户项目';

-- --------------------------------------------------------------------------
-- 4. 洁净室表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cleanroom (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  project_id      BIGINT       NOT NULL COMMENT '所属项目',
  name            VARCHAR(100) NOT NULL COMMENT '洁净室名称',
  code            VARCHAR(50)  NULL COMMENT '洁净室编号',
  remark          VARCHAR(255) NULL COMMENT '备注',
  status          VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'active/deleted，逻辑删除',
  created_by      BIGINT       NOT NULL COMMENT '创建人',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_cleanroom_project_status (project_id, status),
  KEY idx_cleanroom_code (code),
  KEY idx_cleanroom_created_by (created_by),
  CONSTRAINT fk_cleanroom_project FOREIGN KEY (project_id) REFERENCES project (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_cleanroom_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_cleanroom_status CHECK (status IN ('active', 'deleted'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='洁净室档案';

-- --------------------------------------------------------------------------
-- 5. 污染物资料表。仅用于展示、单位换算和标准匹配，不生成 C0/G。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pollutant (
  id                  BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  name_cn             VARCHAR(100) NOT NULL COMMENT '中文名称',
  name_en             VARCHAR(100) NULL COMMENT '英文名称',
  aliases             JSON         NULL COMMENT '别名数组，用于同 CAS 别名治理',
  formula             VARCHAR(50)  NULL COMMENT '化学式',
  molecular_formula   VARCHAR(50)  NULL COMMENT '分子式',
  cas_no              VARCHAR(20)  NULL COMMENT 'CAS 文本，禁止日期格式',
  boiling_point       DECIMAL(9,2) NULL COMMENT '沸点，摄氏度',
  molar_mass          DECIMAL(9,3) NULL COMMENT '摩尔质量 g/mol，仅作资料和默认换算值',
  status              VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'active/disabled',
  created_by          BIGINT       NOT NULL COMMENT '创建人',
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_pollutant_cas_no (cas_no),
  KEY idx_pollutant_name_cn (name_cn),
  KEY idx_pollutant_name_en (name_en),
  KEY idx_pollutant_status (status),
  CONSTRAINT fk_pollutant_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_pollutant_status CHECK (status IN ('active', 'disabled')),
  CONSTRAINT chk_pollutant_molar_mass CHECK (molar_mass IS NULL OR molar_mass > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='污染物资料库';

-- --------------------------------------------------------------------------
-- 6. 标准库表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS std_library (
  id              BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  pollutant_id    BIGINT        NOT NULL COMMENT '污染物',
  customer_id     BIGINT        NULL COMMENT '客户标准所属客户；行业/企业标准可为空',
  source_type     VARCHAR(20)   NOT NULL COMMENT 'industry/enterprise/customer',
  std_name        VARCHAR(100)  NULL COMMENT '标准名称或编号',
  std_value       DECIMAL(18,6) NOT NULL COMMENT '标准值',
  unit            VARCHAR(10)   NOT NULL COMMENT 'ppb/ugm3',
  scope           VARCHAR(100)  NULL COMMENT '适用范围',
  priority        INT           NOT NULL DEFAULT 0 COMMENT '优先级，数值越大优先级越高',
  version         VARCHAR(50)   NULL COMMENT '标准版本',
  effective       TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否生效',
  effective_from  DATE          NULL COMMENT '生效日期',
  effective_to    DATE          NULL COMMENT '失效日期',
  created_by      BIGINT        NOT NULL COMMENT '创建人',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_std_pollutant_source (pollutant_id, source_type, effective),
  KEY idx_std_customer_source (customer_id, source_type, effective),
  KEY idx_std_priority (priority),
  CONSTRAINT fk_std_pollutant FOREIGN KEY (pollutant_id) REFERENCES pollutant (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_std_customer FOREIGN KEY (customer_id) REFERENCES customer (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_std_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_std_source CHECK (source_type IN ('industry', 'enterprise', 'customer')),
  CONSTRAINT chk_std_unit CHECK (unit IN ('ppb', 'ugm3')),
  CONSTRAINT chk_std_value CHECK (std_value >= 0),
  CONSTRAINT chk_std_effective CHECK (effective IN (0, 1)),
  CONSTRAINT chk_std_date_range CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='达标标准库';

-- --------------------------------------------------------------------------
-- 7. 方案表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheme (
  id                  BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  cleanroom_id        BIGINT        NOT NULL COMMENT '所属洁净室',
  name                VARCHAR(100)  NOT NULL COMMENT '方案名称',
  version             INT           NOT NULL DEFAULT 1 COMMENT '版本号',
  source_scheme_id    BIGINT        NULL COMMENT '复制来源方案',
  conc_unit           VARCHAR(10)   NOT NULL DEFAULT 'ugm3' COMMENT '输入和显示单位 ppb/ugm3',
  molar_mass_m        DECIMAL(18,6) NULL COMMENT '用户确认的摩尔质量 M 快照来源',
  molar_volume_vm     DECIMAL(18,6) NOT NULL DEFAULT 24.040000 COMMENT '摩尔体积 Vm L/mol',
  std_source          VARCHAR(20)   NOT NULL DEFAULT 'manual' COMMENT 'industry/enterprise/customer/manual',
  std_pollutant_id    BIGINT        NULL COMMENT '关联污染物；manual 时允许为空',
  std_library_id      BIGINT        NULL COMMENT '选用的标准库记录；manual 时为空',
  target_value        DECIMAL(18,6) NULL COMMENT '目标值；为空时结论 no_standard',
  status              VARCHAR(10)   NOT NULL DEFAULT 'draft' COMMENT 'draft/saved/deleted',
  created_by          BIGINT        NOT NULL COMMENT '创建人',
  created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_scheme_cleanroom_status (cleanroom_id, status),
  KEY idx_scheme_cleanroom_name (cleanroom_id, name),
  KEY idx_scheme_pollutant (std_pollutant_id),
  KEY idx_scheme_std_library (std_library_id),
  KEY idx_scheme_created_by (created_by),
  CONSTRAINT fk_scheme_cleanroom FOREIGN KEY (cleanroom_id) REFERENCES cleanroom (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_scheme_source FOREIGN KEY (source_scheme_id) REFERENCES scheme (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_scheme_pollutant FOREIGN KEY (std_pollutant_id) REFERENCES pollutant (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_scheme_std_library FOREIGN KEY (std_library_id) REFERENCES std_library (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_scheme_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_scheme_version CHECK (version > 0),
  CONSTRAINT chk_scheme_conc_unit CHECK (conc_unit IN ('ppb', 'ugm3')),
  CONSTRAINT chk_scheme_molar_mass CHECK (molar_mass_m IS NULL OR molar_mass_m > 0),
  CONSTRAINT chk_scheme_molar_volume CHECK (molar_volume_vm > 0),
  CONSTRAINT chk_scheme_std_source CHECK (std_source IN ('industry', 'enterprise', 'customer', 'manual')),
  CONSTRAINT chk_scheme_target CHECK (target_value IS NULL OR target_value >= 0),
  CONSTRAINT chk_scheme_status CHECK (status IN ('draft', 'saved', 'deleted')),
  CONSTRAINT chk_scheme_manual_standard CHECK (
    (std_source = 'manual' AND std_library_id IS NULL)
    OR std_source IN ('industry', 'enterprise', 'customer')
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AMC 模拟方案';

-- --------------------------------------------------------------------------
-- 8. 当前方案输入表，与 scheme 一对一，可被后续编辑覆盖。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheme_input (
  id              BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  scheme_id       BIGINT        NOT NULL COMMENT '方案，一对一',
  c0              DECIMAL(18,6) NOT NULL COMMENT '室外浓度 C0，按方案单位录入',
  g               DECIMAL(18,6) NOT NULL COMMENT '室内释放折算 G，按方案单位录入',
  eta_mau         DECIMAL(9,6)  NOT NULL COMMENT 'MAU 效率 0-1',
  cov_mau         DECIMAL(9,6)  NOT NULL COMMENT 'MAU 覆盖率 0-1',
  eta_ceil        DECIMAL(9,6)  NOT NULL COMMENT 'Ceiling 效率 0-1',
  cov_ceil        DECIMAL(9,6)  NOT NULL COMMENT 'Ceiling 覆盖率 0-1',
  eta_aru         DECIMAL(9,6)  NOT NULL COMMENT 'ARU 效率 0-1',
  cov_aru         DECIMAL(9,6)  NOT NULL COMMENT 'ARU 覆盖率 0-1',
  alpha           DECIMAL(9,6)  NOT NULL COMMENT '新风比例 0-1',
  beta            DECIMAL(9,6)  NOT NULL COMMENT '回风比例 0-1',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_scheme_input_scheme (scheme_id),
  CONSTRAINT fk_scheme_input_scheme FOREIGN KEY (scheme_id) REFERENCES scheme (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_scheme_input_c0 CHECK (c0 >= 0),
  CONSTRAINT chk_scheme_input_g CHECK (g >= 0),
  CONSTRAINT chk_scheme_input_eta_mau CHECK (eta_mau BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_cov_mau CHECK (cov_mau BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_eta_ceil CHECK (eta_ceil BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_cov_ceil CHECK (cov_ceil BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_eta_aru CHECK (eta_aru BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_cov_aru CHECK (cov_aru BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_alpha CHECK (alpha BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_beta CHECK (beta BETWEEN 0 AND 1),
  CONSTRAINT chk_scheme_input_ratio CHECK (alpha + beta = 1.000000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='方案当前输入参数';

-- --------------------------------------------------------------------------
-- 9. 不可变计算输入快照。每次计算单独写入，禁止复用或覆盖。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calc_input_snapshot (
  id                  BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  scheme_id           BIGINT        NOT NULL COMMENT '计算时所属方案',
  conc_unit           VARCHAR(10)   NOT NULL COMMENT '用户输入/显示单位 ppb/ugm3',
  c0_original         DECIMAL(18,6) NOT NULL COMMENT '原始输入 C0',
  g_original          DECIMAL(18,6) NOT NULL COMMENT '原始输入 G',
  c0_internal         DECIMAL(18,6) NOT NULL COMMENT '换算后的 C0，单位 ugm3',
  g_internal          DECIMAL(18,6) NOT NULL COMMENT '换算后的 G，单位 ugm3',
  eta_mau             DECIMAL(9,6)  NOT NULL COMMENT 'MAU 效率',
  cov_mau             DECIMAL(9,6)  NOT NULL COMMENT 'MAU 覆盖率',
  eta_ceil            DECIMAL(9,6)  NOT NULL COMMENT 'Ceiling 效率',
  cov_ceil            DECIMAL(9,6)  NOT NULL COMMENT 'Ceiling 覆盖率',
  eta_aru             DECIMAL(9,6)  NOT NULL COMMENT 'ARU 效率',
  cov_aru             DECIMAL(9,6)  NOT NULL COMMENT 'ARU 覆盖率',
  alpha               DECIMAL(9,6)  NOT NULL COMMENT '新风比例',
  beta                DECIMAL(9,6)  NOT NULL COMMENT '回风比例',
  molar_mass_m        DECIMAL(18,6) NULL COMMENT '本次换算使用的 M',
  molar_volume_vm     DECIMAL(18,6) NOT NULL COMMENT '本次换算使用的 Vm',
  epsilon             DECIMAL(18,12) NOT NULL COMMENT '收敛阈值',
  max_iterations      INT           NOT NULL COMMENT '最大迭代次数',
  std_source          VARCHAR(20)   NOT NULL COMMENT '标准来源快照',
  std_pollutant_id    BIGINT        NULL COMMENT '污染物快照关联',
  std_library_id      BIGINT        NULL COMMENT '标准库快照关联',
  target_value        DECIMAL(18,6) NULL COMMENT '原单位目标值快照',
  input_full_precision JSON         NOT NULL COMMENT '原始及内部未舍入值，数值以字符串保存',
  created_by          BIGINT        NOT NULL COMMENT '计算操作者',
  created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
  PRIMARY KEY (id),
  KEY idx_snapshot_scheme_time (scheme_id, created_at),
  KEY idx_snapshot_created_by (created_by),
  CONSTRAINT fk_snapshot_scheme FOREIGN KEY (scheme_id) REFERENCES scheme (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_snapshot_pollutant FOREIGN KEY (std_pollutant_id) REFERENCES pollutant (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_snapshot_std_library FOREIGN KEY (std_library_id) REFERENCES std_library (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_snapshot_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_snapshot_unit CHECK (conc_unit IN ('ppb', 'ugm3')),
  CONSTRAINT chk_snapshot_concentration CHECK (c0_original >= 0 AND g_original >= 0 AND c0_internal >= 0 AND g_internal >= 0),
  CONSTRAINT chk_snapshot_efficiencies CHECK (
    eta_mau BETWEEN 0 AND 1 AND cov_mau BETWEEN 0 AND 1
    AND eta_ceil BETWEEN 0 AND 1 AND cov_ceil BETWEEN 0 AND 1
    AND eta_aru BETWEEN 0 AND 1 AND cov_aru BETWEEN 0 AND 1
  ),
  CONSTRAINT chk_snapshot_ratio CHECK (alpha BETWEEN 0 AND 1 AND beta BETWEEN 0 AND 1 AND alpha + beta = 1.000000),
  CONSTRAINT chk_snapshot_conversion CHECK (molar_volume_vm > 0 AND (conc_unit <> 'ppb' OR molar_mass_m > 0)),
  CONSTRAINT chk_snapshot_iteration CHECK (epsilon > 0 AND max_iterations > 0),
  CONSTRAINT chk_snapshot_std_source CHECK (std_source IN ('industry', 'enterprise', 'customer', 'manual'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='不可变计算输入快照';

-- --------------------------------------------------------------------------
-- 10. 计算结果表。节点数值以内部单位 ugm3 保存。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calc_result (
  id                    BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  scheme_id             BIGINT        NOT NULL COMMENT '所属方案',
  input_snapshot_id     BIGINT        NOT NULL COMMENT '不可变输入快照',
  c0                    DECIMAL(18,6) NOT NULL COMMENT '室外浓度 C0',
  c1                    DECIMAL(18,6) NOT NULL COMMENT 'MAU 下游 C1/Cout1',
  c_return              DECIMAL(18,6) NOT NULL COMMENT 'ARU 下游 C_return/Cout3',
  cmix                  DECIMAL(18,6) NOT NULL COMMENT '混合浓度 Cmix',
  cout2                 DECIMAL(18,6) NOT NULL COMMENT 'Ceiling 本体出口，不含覆盖率',
  cr                    DECIMAL(18,6) NOT NULL COMMENT '最终稳态浓度 Cr',
  result_full_precision JSON          NOT NULL COMMENT '未舍入节点值，数值以字符串保存',
  conclusion            VARCHAR(20)   NOT NULL COMMENT 'pass/fail/no_standard/not_converged/error',
  std_source_snapshot   VARCHAR(20)   NOT NULL COMMENT '标准来源快照',
  std_name_snapshot     VARCHAR(100)  NULL COMMENT '标准名称快照',
  std_version_snapshot  VARCHAR(50)   NULL COMMENT '标准版本快照',
  std_value_snapshot    DECIMAL(18,6) NULL COMMENT '换算为 ugm3 的标准值快照',
  algo_version          VARCHAR(20)   NOT NULL COMMENT '算法版本',
  converged             TINYINT(1)    NOT NULL COMMENT '是否收敛',
  iter_count            INT           NOT NULL COMMENT '迭代次数',
  error_code            VARCHAR(30)   NULL COMMENT '未收敛或退化工况错误码',
  error_message         VARCHAR(255)  NULL COMMENT '异常说明',
  calculation_ms        INT           NULL COMMENT '计算耗时毫秒',
  request_id            VARCHAR(64)   NULL COMMENT '接口 requestId',
  created_by            BIGINT        NOT NULL COMMENT '计算操作者',
  calc_time             DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
  created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_calc_result_snapshot (input_snapshot_id),
  KEY idx_calc_result_scheme_time (scheme_id, calc_time DESC),
  KEY idx_calc_result_conclusion_time (conclusion, calc_time),
  KEY idx_calc_result_created_by (created_by),
  KEY idx_calc_result_request_id (request_id),
  CONSTRAINT fk_calc_result_scheme FOREIGN KEY (scheme_id) REFERENCES scheme (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_calc_result_snapshot FOREIGN KEY (input_snapshot_id) REFERENCES calc_input_snapshot (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_calc_result_created_by FOREIGN KEY (created_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_calc_result_conclusion CHECK (conclusion IN ('pass', 'fail', 'no_standard', 'not_converged', 'error')),
  CONSTRAINT chk_calc_result_converged CHECK (converged IN (0, 1)),
  CONSTRAINT chk_calc_result_iter_count CHECK (iter_count >= 0),
  CONSTRAINT chk_calc_result_state CHECK (
    (converged = 1 AND conclusion IN ('pass', 'fail', 'no_standard'))
    OR (converged = 0 AND conclusion IN ('not_converged', 'error'))
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='不可变稳态计算结果';

-- --------------------------------------------------------------------------
-- 11. 迭代过程表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calc_iter (
  id                  BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  calc_result_id      BIGINT        NOT NULL COMMENT '计算结果',
  iter_no             INT           NOT NULL COMMENT '迭代序号，从 1 开始',
  cr_old              DECIMAL(18,6) NOT NULL COMMENT '本轮计算前 Cr',
  c1                  DECIMAL(18,6) NOT NULL COMMENT 'C1',
  c_return            DECIMAL(18,6) NOT NULL COMMENT 'C_return',
  cmix                DECIMAL(18,6) NOT NULL COMMENT 'Cmix',
  cout2               DECIMAL(18,6) NOT NULL COMMENT 'Cout2，不含 Ceiling 覆盖率',
  cr_new              DECIMAL(18,6) NOT NULL COMMENT '本轮计算后 Cr',
  delta_value         DECIMAL(18,12) NOT NULL COMMENT '|Cr_new-Cr_old|',
  iteration_full_precision JSON      NOT NULL COMMENT '本轮未舍入值，数值以字符串保存',
  created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_calc_iter_result_no (calc_result_id, iter_no),
  CONSTRAINT fk_calc_iter_result FOREIGN KEY (calc_result_id) REFERENCES calc_result (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_calc_iter_no CHECK (iter_no > 0),
  CONSTRAINT chk_calc_iter_delta CHECK (delta_value >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='不可变计算迭代过程';

-- --------------------------------------------------------------------------
-- 12. 报告记录表。必须关联具体 calc_result，不能只关联可变方案。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_record (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  report_no       VARCHAR(50)  NOT NULL COMMENT '报告编号',
  calc_result_id  BIGINT       NOT NULL COMMENT '具体计算结果',
  scheme_id       BIGINT       NOT NULL COMMENT '冗余方案 ID，便于查询',
  report_type     VARCHAR(10)  NOT NULL COMMENT 'excel/pdf',
  file_name       VARCHAR(255) NOT NULL COMMENT '文件名',
  file_path       VARCHAR(500) NOT NULL COMMENT '文件路径或对象存储标识',
  file_hash       VARCHAR(64)  NULL COMMENT 'SHA-256，用于完整性校验',
  generated_by    BIGINT       NOT NULL COMMENT '生成人',
  generated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_report_no (report_no),
  KEY idx_report_result (calc_result_id),
  KEY idx_report_scheme_time (scheme_id, generated_at DESC),
  KEY idx_report_generated_by (generated_by),
  CONSTRAINT fk_report_result FOREIGN KEY (calc_result_id) REFERENCES calc_result (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_report_scheme FOREIGN KEY (scheme_id) REFERENCES scheme (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_report_generated_by FOREIGN KEY (generated_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_report_type CHECK (report_type IN ('excel', 'pdf'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='报告生成记录';

-- --------------------------------------------------------------------------
-- 13. 导入记录表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_record (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  import_type     VARCHAR(20)  NOT NULL COMMENT 'pollutant/standard',
  template_version VARCHAR(30) NULL COMMENT '导入模板版本',
  file_name       VARCHAR(255) NOT NULL COMMENT '原文件名',
  file_hash       VARCHAR(64)  NOT NULL COMMENT 'SHA-256',
  stage           VARCHAR(20)  NOT NULL COMMENT 'validated/imported/failed',
  total_rows      INT          NOT NULL DEFAULT 0 COMMENT '总行数',
  valid_rows      INT          NOT NULL DEFAULT 0 COMMENT '有效行数',
  warning_rows    INT          NOT NULL DEFAULT 0 COMMENT '警告行数',
  error_rows      INT          NOT NULL DEFAULT 0 COMMENT '错误行数',
  duplicate_rows  INT          NOT NULL DEFAULT 0 COMMENT '重复行数',
  result_file_path VARCHAR(500) NULL COMMENT '校验/执行结果文件',
  detail_json     JSON         NULL COMMENT '字段级警告和错误',
  imported_by     BIGINT       NOT NULL COMMENT '操作者',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  finished_at     DATETIME     NULL COMMENT '完成时间',
  PRIMARY KEY (id),
  KEY idx_import_type_time (import_type, created_at DESC),
  KEY idx_import_hash (file_hash),
  KEY idx_import_user (imported_by),
  CONSTRAINT fk_import_user FOREIGN KEY (imported_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_import_type CHECK (import_type IN ('pollutant', 'standard')),
  CONSTRAINT chk_import_stage CHECK (stage IN ('validated', 'imported', 'failed')),
  CONSTRAINT chk_import_counts CHECK (
    total_rows >= 0 AND valid_rows >= 0 AND warning_rows >= 0
    AND error_rows >= 0 AND duplicate_rows >= 0
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Excel 导入预校验与执行记录';

-- --------------------------------------------------------------------------
-- 14. 数据导出记录表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS export_record (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  export_type     VARCHAR(30)  NOT NULL COMMENT 'report/data/backup_assist',
  export_scope    JSON         NULL COMMENT '导出条件与数据范围',
  file_name       VARCHAR(255) NOT NULL COMMENT '文件名',
  file_path       VARCHAR(500) NOT NULL COMMENT '文件路径或对象存储标识',
  file_hash       VARCHAR(64)  NULL COMMENT 'SHA-256',
  status          VARCHAR(20)  NOT NULL DEFAULT 'success' COMMENT 'processing/success/failed',
  error_message   VARCHAR(500) NULL COMMENT '失败原因',
  exported_by     BIGINT       NOT NULL COMMENT '操作者',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  finished_at     DATETIME     NULL COMMENT '完成时间',
  PRIMARY KEY (id),
  KEY idx_export_type_time (export_type, created_at DESC),
  KEY idx_export_user (exported_by),
  CONSTRAINT fk_export_user FOREIGN KEY (exported_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_export_type CHECK (export_type IN ('report', 'data', 'backup_assist')),
  CONSTRAINT chk_export_status CHECK (status IN ('processing', 'success', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='数据导出记录';

-- --------------------------------------------------------------------------
-- 15. 备份与恢复记录表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backup_record (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  backup_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '备份时间',
  file_path       VARCHAR(500) NOT NULL COMMENT '备份文件路径或标识',
  file_hash       VARCHAR(64)  NULL COMMENT 'SHA-256',
  type            VARCHAR(10)  NOT NULL COMMENT 'daily/monthly/manual',
  status          VARCHAR(20)  NOT NULL DEFAULT 'success' COMMENT 'processing/success/failed',
  restored        TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否曾用于恢复',
  restored_at     DATETIME     NULL COMMENT '恢复时间',
  operator_user_id BIGINT      NOT NULL COMMENT '操作用户',
  operator        VARCHAR(50)  NULL COMMENT '操作人姓名快照',
  remark          VARCHAR(500) NULL COMMENT '备注或失败原因',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_backup_time (backup_time DESC),
  KEY idx_backup_status (status),
  KEY idx_backup_operator (operator_user_id),
  CONSTRAINT fk_backup_operator FOREIGN KEY (operator_user_id) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_backup_type CHECK (type IN ('daily', 'monthly', 'manual')),
  CONSTRAINT chk_backup_status CHECK (status IN ('processing', 'success', 'failed')),
  CONSTRAINT chk_backup_restored CHECK (restored IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='备份与恢复记录';

-- --------------------------------------------------------------------------
-- 16. 操作日志表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operation_log (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id         BIGINT       NULL COMMENT '操作用户；登录失败时可为空',
  username_snapshot VARCHAR(50) NULL COMMENT '用户名快照',
  action          VARCHAR(50)  NOT NULL COMMENT '操作类型',
  target_type     VARCHAR(50)  NULL COMMENT '对象类型',
  target_id       BIGINT       NULL COMMENT '对象 ID',
  target          VARCHAR(100) NULL COMMENT '对象显示名称',
  detail          VARCHAR(500) NULL COMMENT '脱敏后的操作详情',
  request_id      VARCHAR(64)  NULL COMMENT '接口 requestId',
  ip_address      VARCHAR(45)  NULL COMMENT 'IPv4/IPv6',
  result_status   VARCHAR(20)  NOT NULL DEFAULT 'success' COMMENT 'success/failed/denied',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (id),
  KEY idx_operation_user_time (user_id, created_at DESC),
  KEY idx_operation_action_time (action, created_at DESC),
  KEY idx_operation_target (target_type, target_id),
  KEY idx_operation_request_id (request_id),
  CONSTRAINT fk_operation_user FOREIGN KEY (user_id) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_operation_status CHECK (result_status IN ('success', 'failed', 'denied'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='关键操作审计日志';

-- --------------------------------------------------------------------------
-- 17. 系统计算参数表
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_config (
  id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  config_key      VARCHAR(100) NOT NULL COMMENT '配置键',
  config_value    VARCHAR(500) NOT NULL COMMENT '配置值',
  value_type      VARCHAR(20)  NOT NULL DEFAULT 'string' COMMENT 'string/integer/decimal/boolean/json',
  description     VARCHAR(255) NULL COMMENT '配置说明',
  version         INT          NOT NULL DEFAULT 1 COMMENT '配置版本',
  status          VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'active/disabled',
  updated_by      BIGINT       NOT NULL COMMENT '最后修改人',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_system_config_key (config_key),
  KEY idx_system_config_status (status),
  CONSTRAINT fk_system_config_user FOREIGN KEY (updated_by) REFERENCES sys_user (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT chk_system_config_type CHECK (value_type IN ('string', 'integer', 'decimal', 'boolean', 'json')),
  CONSTRAINT chk_system_config_version CHECK (version > 0),
  CONSTRAINT chk_system_config_status CHECK (status IN ('active', 'disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='版本化系统计算参数';

-- --------------------------------------------------------------------------
-- 查询视图：每个有效方案的最近一次计算结果
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_scheme_latest_result AS
SELECT ranked.*
FROM (
  SELECT
    cr.id AS calc_result_id,
    cr.scheme_id,
    s.cleanroom_id,
    s.name AS scheme_name,
    cr.cr,
    cr.conclusion,
    cr.converged,
    cr.iter_count,
    cr.algo_version,
    cr.calc_time,
    ROW_NUMBER() OVER (PARTITION BY cr.scheme_id ORDER BY cr.calc_time DESC, cr.id DESC) AS row_no
  FROM calc_result cr
  INNER JOIN scheme s ON s.id = cr.scheme_id
  WHERE s.status <> 'deleted'
) ranked
WHERE ranked.row_no = 1;

-- --------------------------------------------------------------------------
-- 历史计算数据不可变约束
-- --------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_calc_input_snapshot_no_update;
DROP TRIGGER IF EXISTS trg_calc_input_snapshot_no_delete;
DROP TRIGGER IF EXISTS trg_calc_result_no_update;
DROP TRIGGER IF EXISTS trg_calc_result_no_delete;
DROP TRIGGER IF EXISTS trg_calc_iter_no_update;
DROP TRIGGER IF EXISTS trg_calc_iter_no_delete;

DELIMITER $$

CREATE TRIGGER trg_calc_input_snapshot_no_update
BEFORE UPDATE ON calc_input_snapshot
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'calc_input_snapshot is immutable';
END$$

CREATE TRIGGER trg_calc_input_snapshot_no_delete
BEFORE DELETE ON calc_input_snapshot
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'calc_input_snapshot cannot be deleted';
END$$

CREATE TRIGGER trg_calc_result_no_update
BEFORE UPDATE ON calc_result
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'calc_result is immutable';
END$$

CREATE TRIGGER trg_calc_result_no_delete
BEFORE DELETE ON calc_result
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'calc_result cannot be deleted';
END$$

CREATE TRIGGER trg_calc_iter_no_update
BEFORE UPDATE ON calc_iter
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'calc_iter is immutable';
END$$

CREATE TRIGGER trg_calc_iter_no_delete
BEFORE DELETE ON calc_iter
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'calc_iter cannot be deleted';
END$$

DELIMITER ;

-- --------------------------------------------------------------------------
-- 初始化提示
-- --------------------------------------------------------------------------
-- sys_user.password_hash 必须由后端使用 Argon2id 或 bcrypt 生成，禁止在 SQL 中
-- 写入演示账号明文密码。首次管理员账号应通过部署初始化程序创建。
--
-- 建议由部署程序在管理员创建后写入以下 system_config：
--   calculation.epsilon          = 0.000001
--   calculation.max_iterations   = 200
--   conversion.molar_volume_vm   = 24.04
--   calculation.algo_version     = steady-v1.0
--
-- 方案计算的推荐事务顺序：
--   1. INSERT calc_input_snapshot
--   2. INSERT calc_result
--   3. 批量 INSERT calc_iter
--   4. INSERT operation_log
-- 任一步失败应 ROLLBACK，禁止留下半成品结果。
