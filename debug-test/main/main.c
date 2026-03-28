#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "sdkconfig.h"

#if defined(CONFIG_IDF_TARGET_ESP32)
#define LED_GPIO 2
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
#define LED_GPIO 2
#else
#define LED_GPIO 8
#endif

volatile int loop_counter = 0;

void __attribute__((noinline)) debug_loop(void) {
    loop_counter++;
    printf("LOOP: %d\n", loop_counter);
    gpio_set_level(LED_GPIO, loop_counter % 2);
    vTaskDelay(pdMS_TO_TICKS(500));
}

void app_main(void) {
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);

    printf("DEBUG_TEST_READY\n");

    while (1) {
        debug_loop();
    }
}
