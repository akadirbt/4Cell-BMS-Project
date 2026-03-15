#include "stm32f4xx.h"  // STM32F4 standard peripheral definitions
#include <stdio.h>
#include <string.h>

#define CELL_COUNT 4      // Total number of battery cells
#define SAMPLE_TOTAL 64   // Number of ADC samples per cell for averaging

// ADC reading
volatile uint16_t adc_values[CELL_COUNT];  // Latest DMA readings
volatile uint16_t cell_samples[CELL_COUNT][SAMPLE_TOTAL];  // Circular buffer for each cell
volatile uint8_t current_sample = 0;  // Current index in sample buffer

// Processed voltages and communication
float cell_voltage[CELL_COUNT];   // Calculated voltages for each cell
char message[64];                 // UART transmit buffer
char command[32];                 // UART command input buffer
uint8_t fan_state = 0;            // Fan status flag (0=off, 1=on)

// Delay func.
void wait_ms(uint32_t ms) {
    for (uint32_t i = 0; i < ms * 4000; i++) {
        __NOP();
    }
}

// Set up GPIOs fan direction
void Fan_Pin_Setup(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    GPIOA->MODER |= (1 << (0 * 2)) | (1 << (1 * 2));
    GPIOA->ODR |= (1 << 0);
    GPIOA->ODR &= ~(1 << 1);
}

// Set up PWM signal for fan speed control
void Fan_PWM_Setup(void) {
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    GPIOA->MODER |= (2 << (2 * 2));
    GPIOA->AFR[0] |= (1 << (2 * 4));

    TIM2->PSC = 160 - 1;       // Prescaler for 100 kHz
    TIM2->ARR = 1000 - 1;      // PWM period for 1 kHz
    TIM2->CCR3 = 0;            // Initial duty = 0%

    TIM2->CCMR2 |= (6 << 4);   // PWM mode 1
    TIM2->CCMR2 |= TIM_CCMR2_OC3PE;
    TIM2->CCER |= TIM_CCER_CC3E;
    TIM2->CR1 |= TIM_CR1_CEN;  // Start timer
}

// Set fan speed by duty cycle percentage
void Fan_Set_Speed(uint8_t speed_percent) {
    if (speed_percent > 100) speed_percent = 100;
    TIM2->CCR3 = (TIM2->ARR + 1) * speed_percent / 100;
}

// PA0–PA3 pins for analog inputs for ADC
void Cell_Pin_Setup(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    GPIOA->MODER |= (3 << (0 * 2)) | (3 << (1 * 2)) | (3 << (2 * 2)) | (3 << (3 * 2));
}

// PD12–PD15 pins for outputs to control cell discharge MOSFETs
void Mosfet_Pin_Setup(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIODEN;
    GPIOD->MODER |= (1 << (12 * 2)) | (1 << (13 * 2)) | (1 << (14 * 2)) | (1 << (15 * 2));
    GPIOD->OTYPER &= ~((1 << 12) | (1 << 13) | (1 << 14) | (1 << 15));
    GPIOD->OSPEEDR |= (3 << (12 * 2)) | (3 << (13 * 2)) | (3 << (14 * 2)) | (3 << (15 * 2));
}

// DMA2 Stream0 for ADC1
void DMA_Setup(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_DMA2EN;

    DMA2_Stream0->CR &= ~DMA_SxCR_EN;
    while (DMA2_Stream0->CR & DMA_SxCR_EN);

    DMA2_Stream0->PAR  = (uint32_t)&ADC1->DR;
    DMA2_Stream0->M0AR = (uint32_t)adc_values;
    DMA2_Stream0->NDTR = CELL_COUNT;

    DMA2_Stream0->CR = 0;
    DMA2_Stream0->CR |= (0 << 25) | DMA_SxCR_PL_1 | DMA_SxCR_MSIZE_0 |
                        DMA_SxCR_PSIZE_0 | DMA_SxCR_MINC | DMA_SxCR_CIRC | DMA_SxCR_EN;
}

// ADC1 settings for continuous scan mode with DMA
void ADC_Setup(void) {
    RCC->APB2ENR |= RCC_APB2ENR_ADC1EN;

    ADC1->CR1 = ADC_CR1_SCAN;
    ADC1->CR2 = ADC_CR2_DMA | ADC_CR2_DDS | ADC_CR2_CONT | ADC_CR2_ADON;

    ADC1->SQR1 = (CELL_COUNT - 1) << 20;
    ADC1->SQR3 = (0 << 0) | (1 << 5) | (2 << 10) | (3 << 15);
    ADC1->SMPR2 = 0xFFFFFFFF;
}

// Start ADC1
void ADC_Start_Read(void) {
    ADC1->CR2 |= ADC_CR2_SWSTART;
}

// Copy latest ADC readings
void ADC_Copy_Readings(void) {
    for (uint8_t i = 0; i < CELL_COUNT; i++) {
        cell_samples[i][current_sample] = adc_values[i];
    }
    current_sample = (current_sample + 1) % SAMPLE_TOTAL;
}

// Average ADC value of the specified cell (Avarage of last 64 values)
float Get_Cell_Average(uint8_t cell_number) {
    uint32_t total = 0;
    for (uint8_t i = 0; i < SAMPLE_TOTAL; i++) {
        total += cell_samples[cell_number][i];
    }
    return (float)total / SAMPLE_TOTAL;
}

// Discharge the cell with highest voltage if difference is too high
void Balance_Cells(void) {
    float max_voltage = 0, min_voltage = 100.0f;
    uint8_t max_cell = 0;

    for (uint8_t i = 0; i < CELL_COUNT; i++) {
        cell_voltage[i] = Get_Cell_Average(i) / 4095.0f * 3.3f * 11.0f;  // Voltage calc. with voltage divider for 47k and 4.7k

        if (cell_voltage[i] > max_voltage) {
            max_voltage = cell_voltage[i];
            max_cell = i;
        }
        if (cell_voltage[i] < min_voltage) {
            min_voltage = cell_voltage[i];
        }
    }

    float difference = max_voltage - min_voltage;

    GPIOD->ODR &= ~((1 << 12) | (1 << 13) | (1 << 14) | (1 << 15));  // Turn off all MOSFETs

    if (difference >= 0.1f) {  // Only balance if diff > 100mV
        GPIOD->ODR |= (1 << (12 + max_cell));  // Turn on highest cell's MOSFET
        wait_ms(200);  // Discharge time
        GPIOD->ODR &= ~(1 << (12 + max_cell));
    }
}

// UART1 settings PA9(TX) and PA10(RX)
void UART_Setup(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN;

    GPIOA->MODER &= ~((3 << (9 * 2)) | (3 << (10 * 2)));
    GPIOA->MODER |=  (2 << (9 * 2)) | (2 << (10 * 2));
    GPIOA->AFR[1] &= ~((0xF << ((9 - 8) * 4)) | (0xF << ((10 - 8) * 4)));
    GPIOA->AFR[1] |=  (7 << ((9 - 8) * 4)) | (7 << ((10 - 8) * 4));

    USART1->BRR = 0x8B;  // 115200 baud
    USART1->CR1 |= USART_CR1_TE | USART_CR1_RE;
    USART1->CR1 |= USART_CR1_UE;
}

// Send one character via UART
void UART_Send_Char(char c) {
    while (!(USART1->SR & USART_SR_TXE));
    USART1->DR = c;
}

// Read one character via UART (blocking)
char UART_Read_Char(void) {
    while (!(USART1->SR & USART_SR_RXNE));
    return USART1->DR;
}

// Send string via UART
void UART_Send_Text(const char* text) {
    while (*text) {
        UART_Send_Char(*text++);
    }
}

// Receive string from UART until newline or carriage return
void UART_Read_Command(char* text, uint8_t size) {
    uint8_t i = 0;
    char c;
    while (i < size - 1) {
        c = UART_Read_Char();
        if (c == '\n' || c == '\r') break;
        text[i++] = c;
    }
    text[i] = '\0';
}

// Main program loop
int main(void) {
    Cell_Pin_Setup();         // Set PA0–PA3 as analog inputs
    Mosfet_Pin_Setup();       // Set PD12–15 as output for cell balancing
    DMA_Setup();              // Configure DMA for ADC
    ADC_Setup();              // Configure ADC1
    UART_Setup();             // Initialize UART
    ADC_Start_Read();         // Begin ADC conversions
    Fan_Pin_Setup();          // Set fan direction
    Fan_PWM_Setup();          // Set up fan PWM
    Fan_Set_Speed(0);         // Start with fan off

    while (1) {
        UART_Read_Command(command, sizeof(command));  // Wait for command

        if (strcmp(command, "FAN ON") == 0) {
            Fan_Set_Speed(80);
            fan_state = 1;
            UART_Send_Text("Fan turned ON\r\n");
        } else if (strcmp(command, "FAN OFF") == 0) {
            Fan_Set_Speed(0);
            fan_state = 0;
            UART_Send_Text("Fan turned OFF\r\n");
        }

        ADC_Copy_Readings();    // Read ADC values
        Balance_Cells();        // Perform balancing logic

        for (uint8_t i = 0; i < CELL_COUNT; i++) {
            snprintf(message, sizeof(message), "Cell %d: %.3f V\r\n", i, cell_voltage[i]);
            UART_Send_Text(message);  // Print voltage values
        }

        UART_Send_Text("\r\n");
        wait_ms(1000);  // 1 second delay before next loop
    }
}
