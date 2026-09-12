/****************************************************************************
 * boards/risc-v/esp32p4/esp32p4-function-ev-board/src/esp32p4_ethernet.c
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.  The
 * ASF licenses this file to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance with the
 * License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
 * License for the specific language governing permissions and limitations
 * under the License.
 *
 ****************************************************************************/

/****************************************************************************
 * Included Files
 ****************************************************************************/

#include <nuttx/config.h>

#include <debug.h>
#include <errno.h>

#include "espressif/esp_emac.h"
#include "espressif/esp_hr_timer.h"

#include "esp32p4-function-ev-board.h"

/****************************************************************************
 * Public Functions
 ****************************************************************************/

/****************************************************************************
 * Name: board_emac_init
 *
 * Description:
 *   Bring up the ESP32-P4 Ethernet interface (internal EMAC + external
 *   PHY) and register it with the NuttX network stack.
 *
 * Input Parameters:
 *   None.
 *
 * Returned Value:
 *   0 (OK) on success; a negated errno value on failure.
 *
 ****************************************************************************/

/* SILICONLOOP: 板级源码的 -I 路径不含 HAL 的 esp_timer 头文件目录，
 * 此处直接声明原型，避免引入整套包含路径。
 * 原型见 components/esp_timer/include/esp_timer.h:114
 */

extern int esp_timer_init(void);

volatile int g_sl_hrtimer_ret = 0xdead;
volatile int g_sl_esptimer_ret = 0xdead;
volatile int g_sl_espemac_ret = 0xdead;

int board_emac_init(void)
{
  int ret;

  /* esp_eth_driver_install() relies on esp_timer; make sure the timer
   * subsystem is initialised before creating the driver.
   */

  /* SILICONLOOP: 埋点，区分两个初始化步骤各自的返回值 */

  /* SILICONLOOP: openvela 内核依赖 hr_timer，必须初始化。
   * 与其冲突的 HAL esp_timer 已改用 alarm 1 + TARGET1（见 HAL 补丁）。
   */

  ret = esp_hr_timer_init();
  g_sl_hrtimer_ret = ret;
  if (ret < 0)
    {
      nerr("ERROR: esp_hr_timer_init failed: %d\n", ret);
      return ret;
    }


  /* SILICONLOOP: openvela 的 esp_hr_timer_init() 只初始化 NuttX 自己的
   * SYSTIMER 封装，与 Apache NuttX 中同名函数（位于 esp_timer_adapter.c，
   * 内部调用 esp_timer_init()）行为不同。esp_eth_driver_install() 依赖
   * ESP-IDF 的 esp_timer 子系统，故此处显式初始化，否则
   * esp_timer_create() 返回 ESP_ERR_INVALID_STATE (0x103)。
   */

  {
    int terr = esp_timer_init();
    g_sl_esptimer_ret = terr;
    if (terr != 0 && terr != 0x103)
      {
        nerr("ERROR: esp_timer_init failed: %d\n", terr);
        return -EIO;
      }
  }

  ret = esp_emac_init();
  g_sl_espemac_ret = ret;
  if (ret < 0)
    {
      nerr("ERROR: esp_emac_init failed: %d\n", ret);
    }

  return ret;
}
