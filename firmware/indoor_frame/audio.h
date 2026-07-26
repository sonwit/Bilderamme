// audio.h — enkel lyd-feedback for Fugleramme (ES8311 + I2S)
#pragma once

void audioInit();          // kall en gang i setup()
void audioStartupChime();  // liten jingle ved oppstart
void audioImageChime();    // "pling" naar et bilde er mottatt
