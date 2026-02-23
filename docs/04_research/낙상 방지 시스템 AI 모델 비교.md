# **고성능 인공지능 기반 낙상 방지 시스템 구축을 위한 최적 아키텍처 연구: YOLO11과 MediaPipe의 하이브리드 전략 및 YOLO Pose 단일 체계에 대한 비교 분석**

인구 고령화가 가속화됨에 따라 노인 인구의 안전을 보장하기 위한 기술적 대안으로 비침습적 낙상 방지 시스템의 중요성이 대두되고 있습니다. 과거의 낙상 감지 기술은 가속도계나 자이로스코프와 같은 웨어러블 센서에 의존하였으나, 이러한 방식은 사용자의 착용 번거로움, 배터리 관리의 불편함, 그리고 착용을 잊었을 때의 대응 공백이라는 치명적인 한계를 노출해 왔습니다.1 이에 대한 대안으로 컴퓨터 비전 기반의 시스템이 주목받고 있으며, 특히 객체 탐지와 포즈 추정(Pose Estimation) 기술의 결합은 물리적 접촉 없이도 인간의 복잡한 움직임을 정밀하게 분석할 수 있는 가능성을 제시합니다. 본 보고서에서는 최신 객체 탐지 모델인 YOLO11과 구글의 MediaPipe Pose를 결합한 하이브리드 전략과, YOLOv8 또는 YOLO11 Pose를 이용한 단일 모델 전략의 기술적 특성, 성능 벤치마크, 그리고 실제 환경에서의 적용 가능성을 심층적으로 분석합니다.

## **객체 탐지 아키텍처의 진화와 YOLO11의 기술적 혁신**

낙상 방지 시스템의 중추적인 역할을 담당하는 YOLO(You Only Look Once) 시리즈는 실시간 객체 탐지 분야에서 독보적인 위치를 차지해 왔습니다. 2024년 말 출시된 YOLO11은 이전 세대인 YOLOv8의 견고한 기반 위에 아키텍처적 고도화를 이루어내며 효율성과 정확도의 새로운 기준을 제시하였습니다.3

### **YOLO11의 구조적 개선과 효율성**

YOLO11은 백본(Backbone)과 넥(Neck) 구조를 대폭 개선하여 특징 통합 능력을 강화하였습니다. 특히 CSP(Cross Stage Partial) 블록을 최적화하여 부동 소수점 연산량(FLOPs)을 유의미하게 줄이면서도 평균 정밀도(mAP)를 향상시켰습니다.3 이러한 설계적 진보는 연산 자원이 제한된 엣지 디바이스(Edge Device) 환경에서 더욱 빛을 발합니다. 예를 들어, YOLO11n 모델은 YOLOv8n에 비해 매개변수(Parameters) 수가 약 22% 감소했음에도 불구하고, CPU 상의 ONNX 추론 속도는 약 22% 더 빠르며 더 높은 mAP를 기록하고 있습니다.3

| 모델 변형 | mAP (50-95) | 매개변수 (M) | FLOPs (B) | CPU ONNX 속도 (ms) |
| :---- | :---- | :---- | :---- | :---- |
| YOLOv8n (Nano) | 37.3 | 3.2 | 8.7 | 80.4 |
| YOLO11n (Nano) | 39.5 | 2.6 | 6.5 | 56.1 |
| YOLOv8s (Small) | 44.9 | 11.2 | 28.6 | 128.4 |
| YOLO11s (Small) | 47.0 | 9.4 | 21.5 | 90.0 |
| YOLOv8m (Medium) | 50.2 | 25.9 | 78.9 | 234.7 |
| YOLO11m (Medium) | 51.5 | 20.1 | 68.0 | 183.2 |

위 데이터에서 확인할 수 있듯이, YOLO11은 동일한 연산 자원 내에서 더 정밀한 탐지가 가능하므로, 낙상과 같이 찰나의 순간에 발생하는 사고를 감지하는 데 필수적인 실시간성을 보장합니다.4 특히 나노(Nano) 모델의 경우 매개변수 수가 2.6M에 불과하여 저전력 IoT 센서나 모바일 환경에서의 배터리 보존 측면에서도 우위를 점합니다.3

### **C3K2 블록과 C2PSA 모듈의 역할**

YOLO11의 성능 향상은 새로운 구성 요소인 C3K2 블록과 C2PSA 모듈의 도입에 기인합니다. C3K2 블록은 특징 추출의 효율성을 극대화하며, C2PSA(Convolutional with Parallel Spatial Attention) 모듈은 모델이 이미지 내에서 중요한 시각적 영역(예: 낙상하는 인체와 복잡한 배경의 분리)에 집중할 수 있도록 돕습니다.5 이러한 주의(Attention) 메커니즘은 피사체가 가구 등에 의해 부분적으로 가려지거나 조명이 어두운 실내 환경에서도 인체를 안정적으로 포착하게 해줍니다.5

## **MediaPipe Pose와 YOLO Pose의 포즈 추정 비교 분석**

낙상 감지 시스템에서 인체의 상태를 정의하기 위해서는 단순한 박스 형태의 탐지를 넘어, 관절의 위치를 파악하는 포즈 추정 기술이 필수적입니다. 이 과정에서 MediaPipe Pose와 YOLO Pose는 서로 다른 접근 방식을 취합니다.

### **MediaPipe Pose의 세밀함과 3차원 좌표계**

MediaPipe Pose(BlazePose)는 구글에서 개발한 프레임워크로, 단일 인체 포즈 추정에 최적화되어 있습니다. 이 모델의 가장 큰 특징은 33개의 랜드마크(Landmark)를 제공한다는 점입니다. YOLO Pose가 관절 중심의 17개 키포인트를 제공하는 것과 달리, MediaPipe는 얼굴의 세부 지점과 손가락, 발가락 끝까지 포함하는 조밀한 토폴로지를 가집니다.6

또한 MediaPipe는 각 키포인트에 대해 (x, y) 평면 좌표뿐만 아니라 z축 깊이 정보와 가시성(Visibility) 점수를 함께 제공합니다.8 이는 인체가 카메라를 향해 수직으로 쓰러지는지, 아니면 옆으로 쓰러지는지를 구분하는 데 결정적인 단서를 제공하며, 관절이 신체 다른 부위에 가려지는 자가 폐쇄(Self-occlusion) 상황에서 더 정교한 추론을 가능하게 합니다.8

### **YOLO Pose의 단일 단계 효율성과 다중 인원 지원**

반면 YOLO11 Pose는 객체 탐지와 키포인트 예측을 하나의 네트워크에서 동시에 수행하는 단일 단계(Single-stage) 방식을 사용합니다.6 이 방식은 추론 속도가 매우 빠르며, 한 프레임 내에 여러 명이 동시에 존재하는 환경에서도 각 개인의 포즈를 독립적이고 안정적으로 추적할 수 있는 다중 인원(Multi-person) 지원 능력을 갖추고 있습니다.6

| 비교 항목 | MediaPipe Pose | YOLO11 Pose |
| :---- | :---- | :---- |
| 키포인트 수 | 33개 | 17개 |
| 좌표 차원 | 3D (x, y, z) \+ 가시성 | 2D (x, y) \+ 신뢰도 |
| 처리 방식 | 2단계 (인체 탐지 후 포즈 추정) | 1단계 (탐지 및 포즈 동시 수행) |
| 다중 인원 지원 | 제한적 (단일 인원 최적화) | 기본 지원 (다중 인원 강점) |
| 주요 강점 | 세밀한 동작 분석, 깊이 정보 | 빠른 속도, 군중 속 개별 추적 |

YOLO11 Pose는 COCO 데이터셋 기준 17개 키포인트를 사용하여 어깨, 팔꿈치, 손목, 엉덩이, 무릎, 발목 등 주요 대관절의 움직임을 효과적으로 파악합니다.6 일반적인 실내 낙상 감지 환경에서 33개의 세밀한 포인트가 반드시 필요한 것은 아니며, 오히려 17개의 핵심 관절만으로도 충분한 분석이 가능하다는 연구 결과가 다수 존재합니다.10

## **하이브리드 전략 vs 단일 전략: 선택의 기준**

사용자가 질문한 'YOLO11 \+ MediaPipe 하이브리드'와 'YOLO \+ YOLO Pose 단일 체계' 중 어떤 것이 나은지에 대한 해답은 시스템이 구축될 환경의 특성에 따라 달라집니다.

### **하이브리드 전략의 이점: 정밀도와 심층 분석**

하이브리드 전략은 YOLO11을 인체 탐지기로 사용하여 관심 영역(ROI)을 먼저 확정하고, 해당 영역의 이미지를 잘라내어 MediaPipe Pose에 입력하는 방식입니다.11 이 방식은 다음과 같은 상황에서 유리합니다.

1. **단일 거주자 모니터링:** 독거노인 가정과 같이 한 공간에 한 명만 있는 경우, MediaPipe의 33개 랜드마크는 인체의 비정상적인 기울기나 미세한 떨림을 감지하는 데 더 풍부한 데이터를 제공합니다.7  
2. **동작 분류의 정확도:** 연구에 따르면 1098개의 특징량(33개 랜드마크의 x, y, z 좌표 등)을 사용하는 MediaPipe 기반 파이프라인이 17개 포인트만을 사용하는 YOLO Pose보다 로지스틱 회귀나 LSTM 분류기에서 더 높은 정확도를 보이는 경향이 있습니다.7  
3. **깊이 정보 활용:** z축 좌표를 통해 카메라와의 거리가 급격히 변하는 낙상 궤적을 분석할 수 있어, 단순히 2D 평면상에서 바닥으로 내려가는 동작과 실제로 쓰러지는 동작을 더 잘 구분할 수 있습니다.8

### **단일 전략의 이점: 실시간성과 확장성**

YOLO11 Pose 단일 체계를 사용하는 방식은 시스템의 단순성과 처리 속도에 방점을 둡니다.

1. **다중 인원 환경:** 요양병원 공용 거실이나 병동 복도처럼 여러 환자와 의료진이 섞여 있는 공간에서는 YOLO Pose의 다중 인원 추적 능력이 압도적으로 유리합니다.7 MediaPipe는 다중 인원 처리 시 추적 대상이 바뀌거나 성능이 급격히 저하되는 문제가 발생할 수 있습니다.16  
2. **엣지 컴퓨팅 자원 절약:** 두 개의 모델(YOLO \+ MediaPipe)을 로드하여 순차적으로 실행하는 하이브리드 방식은 연산 오버헤드가 발생합니다. 반면 YOLO11 Pose는 단일 모델만으로 모든 처리를 끝내므로, 임베디드 시스템이나 저성능 서버에서도 30 FPS 이상의 부드러운 분석이 가능합니다.6  
3. **배포 및 유지보수:** 단일 API(예: Ultralytics)를 사용하여 시스템을 구축하면 모델 업데이트나 포맷 변환(TFLite, TensorRT 등)이 용이하며 기술 부채가 적습니다.3

## **낙상 감지 로직의 수학적 및 논리적 구현**

단순히 키포인트를 추출하는 것만으로는 낙상을 확정할 수 없습니다. 추출된 좌표를 기반으로 '사건'을 정의하는 알고리즘이 뒤따라야 합니다.

### **무게중심(Center of Gravity, CoG) 변화 분석**

가장 일반적인 낙상 판단 근거는 인체 무게중심의 급격한 수직 이동입니다. 시스템은 주요 신체 질량 부위인 머리(0), 어깨(5, 6), 엉덩이(11, 12), 무릎(13, 14)의 키포인트를 사용하여 무게중심을 계산합니다.10

![][image1]  
여기서 ![][image2]는 선택된 핵심 관절 세트입니다. 특정 프레임 사이에서 $CoG\_{y}$의 값이 설정된 임계값(Threshold) 이상으로 급격히 증가(이미지 좌표계 기준 아래쪽으로 이동)한다면 이를 낙상의 강력한 징후로 판단합니다.10

### **신체 방향 및 바운딩 박스 종횡비(Aspect Ratio)**

또 다른 보조 지표는 인체를 둘러싼 바운딩 박스의 형태 변화입니다. 서 있는 상태에서는 박스의 높이가 너비보다 길지만, 낙상 시에는 박스가 가로로 길어지게 됩니다.1 또한 어깨 중심점과 골반 중심점을 연결하는 가상의 선이 지면과 이루는 각도를 계산하여, 이 각도가 수직(90도)에서 수평(0\~30도)으로 급변하는 시점을 포착합니다.18

| 상태 지표 | 정상 활동 (Standing/Walking) | 낙상 발생 (Falling/Lying) |
| :---- | :---- | :---- |
| 종횡비 (Height/Width) | \> 1.0 (세로형) | \< 1.0 (가로형) |
| 몸의 기울기 (Trunk Angle) | 60° \~ 90° | 0° \~ 45° |
| 무게중심 속도 (CoG Velocity) | 낮음 | 매우 높음 (급강하) |

## **시계열 데이터 처리를 위한 LSTM 및 GRU 네트워크 통합**

낙상은 단일 프레임의 정지 영상이 아니라 연속적인 동작의 흐름입니다. 단순히 한 프레임에서 사람이 누워 있다고 해서 낙상으로 판단하면, 이미 바닥에 누워 있는 사람이나 앉아 있는 사람을 오진할 위험이 큽니다. 이를 해결하기 위해 10\~20프레임 정도의 키포인트 시퀀스를 분석하는 순환 신경망(RNN) 구조가 도입됩니다.12

### **LSTM과 GRU의 선택**

LSTM(Long Short-Term Memory)은 긴 시간 동안의 동작 패턴을 학습하는 데 유리하지만, 연산량이 많습니다. 최근의 낙상 감지 연구에서는 연산이 더 효율적이면서도 짧은 시퀀스 분석 성능이 뛰어난 GRU(Gated Recurrent Unit)를 선호하는 추세입니다.12

분석 파이프라인은 다음과 같습니다.

1. 포즈 추정 모델을 통해 매 프레임 17개 또는 33개의 키포인트 좌표를 추출합니다.  
2. 결측치(가려진 관절)가 발생할 경우 KNN(K-Nearest Neighbors) 알고리즘 등을 사용하여 이전 프레임의 데이터를 기반으로 보간합니다.20  
3. 정규화된 좌표 데이터를 20프레임 단위의 윈도우(Window)로 묶어 GRU 모델에 입력합니다.  
4. GRU 모델은 해당 시퀀스가 '정상 활동', '낙상 진행 중', '낙상 후 정지 상태' 중 어디에 해당하는지 확률값을 출력합니다.12

이러한 시계열 분석을 통해 정확도를 96% 이상으로 끌어올릴 수 있으며, 특히 의자에 앉는 동작이나 신발 끈을 묶기 위해 숙이는 동작과 실제 낙상을 정밀하게 구분할 수 있습니다.1

## **조도 및 폐쇄(Occlusion) 환경에서의 강건성 확보**

실제 가정 환경은 연구실처럼 이상적인 조명과 탁 트인 시야를 제공하지 않습니다. 가구에 의해 몸의 하반신이 가려지거나, 야간에 불이 꺼진 상태에서도 시스템은 작동해야 합니다.

### **가시성 점수와 가중치 적용**

MediaPipe Pose가 제공하는 가시성(Visibility) 점수는 이러한 상황에서 매우 유용합니다. 특정 관절이 가려졌을 때 해당 데이터의 신뢰도를 낮추고, 가시성이 높은 상체 위주의 데이터를 통해 포즈를 추론하도록 가중치를 조정할 수 있습니다.8 YOLO11 역시 C2PSA 모듈을 통해 이미지의 노이즈를 걸러내고 중요한 피사체 영역에 집중함으로써, 어두운 환경이나 복잡한 배경에서도 인체를 놓치지 않는 강건성을 보여줍니다.5

### **다중 카메라 및 하드웨어 보완**

한 대의 카메라로는 필연적으로 사각지대가 발생합니다. 이를 극복하기 위해 두 대 이상의 카메라를 서로 다른 각도로 배치하고, 각 카메라에서 분석된 낙상 확률을 앙상블(Ensemble)하여 최종 결정을 내리는 방식이 권장됩니다.18 또한 시각 정보에만 의존하지 않고, 낙상 발생 시 AI 음성 비서가 "괜찮으십니까?"라고 묻고 사용자의 음성 응답이 없는 경우에만 긴급 알람을 보내는 하이브리드 인터랙션 모델은 오경보(False Positive)를 75%까지 감소시킵니다.10

## **하드웨어 배포 및 엣지 AI 최적화 전략**

낙상 감지 시스템은 개인정보 보호와 즉각적인 대응을 위해 현장에서 직접 데이터를 처리하는 엣지 컴퓨팅 방식으로 구축되어야 합니다.4

### **모바일 및 임베디드 장치로의 포팅**

YOLO11과 MediaPipe 모두 모바일 친화적인 배포 경로를 제공합니다. YOLO11은 PyTorch 모델을 CoreML(Apple 장치)이나 TFLite(Android, 임베디드 Linux) 포맷으로 변환하여 하드웨어 가속을 활용할 수 있습니다.3 특히 TFLite의 INT8 양자화(Quantization) 기술을 사용하면 정확도 손실을 최소화하면서 모델 크기를 대폭 줄이고 추론 속도를 높일 수 있습니다.3

| 플랫폼 | 가속 기술 | 권장 모델 포맷 | 기대 효과 |
| :---- | :---- | :---- | :---- |
| NVIDIA Jetson | TensorRT | .engine | 수 밀리초 단위의 초고속 추론 |
| Android / IoT | TFLite | .tflite (INT8) | 낮은 전력 소모 및 실시간성 |
| iOS / iPad | CoreML | .mlpackage | 뉴럴 엔진 활용으로 CPU 부하 감소 |
| 웹 브라우저 | WebGPU | WASM / JS | 별도 설치 없는 모니터링 환경 |

Raspberry Pi와 같은 저사양 보드에서는 YOLO11n 모델을 사용하고, 더 높은 정확도가 필요한 서버 환경에서는 YOLO11m 또는 11l 모델을 사용하는 계층적 배포 전략이 유효합니다.4

## **대구광역시 스마트 시티 사례와 지역적 적용**

사용자의 관심사에 포함된 대구광역시의 사례를 통해 기술의 실제 적용 현황을 살펴볼 수 있습니다. 대구광역시는 전국 최초로 AI 상담 시스템을 구축하는 등 ABB(AI, Big Data, Blockchain) 산업을 5대 신산업으로 집중 육성하고 있습니다.23

### **실버 케어와 AI 복지용구 시범 사업**

대구 시내의 요양병원은 이미 AI 기반 모니터링 시스템을 도입하여 200여 개 병상의 환자 활력 징후와 이상 행동을 실시간으로 감지하고 있습니다.24 특히 2026년부터 시행되는 복지용구 예비급여 시범 사업에는 'AI 기반 낙상 보호 에어백'과 '활동 감지 시스템'이 포함되어 있습니다.25

이러한 시스템들은 본 보고서에서 다룬 기술 스택과 궤를 같이합니다.

1. **활동 감지 시스템:** 카메라 또는 레이더 센서를 통해 환자의 심박, 호흡, 침대에서의 자세를 실시간 모니터링하며, 포즈 추정 알고리즘을 통해 위험한 움직임을 사전에 경고합니다.25  
2. **낙상 보호 에어백:** AI 알고리즘이 가속도 센서와 카메라 데이터를 결합 분석하여 낙상 확정 시 에어백을 팽창시키고 보호자 앱으로 신호를 전송합니다.26

대구의 전문 기업들은 사용자의 걸음걸이 패턴을 AI로 분석하여 치매나 파킨슨병 등 질환 발생 가능성을 사전에 예측하는 단계까지 기술을 발전시키고 있습니다.27

## **차세대 기술 전망: YOLO26과 NMS-Free 아키텍처**

기술의 발전 속도는 매우 빠르며, 2026년에 등장한 YOLO26은 낙상 방지 시스템의 성능을 한 단계 더 도약시킬 것으로 기대됩니다. YOLO26의 핵심은 NMS-Free(Non-Maximum Suppression 제거) 설계입니다.3

기존 모델들은 중복된 탐지 상자를 제거하기 위해 NMS라는 후처리 과정을 거치는데, 이는 CPU 연산량을 늘리고 지연 시간(Jitter)을 유발하는 원인이었습니다. YOLO26은 이를 네트워크 내부로 통합하여 CPU 추론 속도를 YOLO11 대비 43% 이상 향상시켰습니다.3 이는 임베디드 기기에서 더 정교한 포즈 추정 모델을 동시에 실행할 수 있는 연산 여유를 제공하며, 더욱 안정적인 실시간 모니터링을 가능하게 합니다.

| 지표 (나노 모델 기준) | YOLO11n | YOLO26n | 개선율 |
| :---- | :---- | :---- | :---- |
| mAP (val 50-95) | 39.5 | 40.9 | \+3.5% |
| CPU 속도 (ms) | 56.1 | 38.9 | \+30.7% |
| 매개변수 (M) | 2.6 | 2.4 | \-7.7% |
| FLOPs (B) | 6.5 | 5.4 | \-16.9% |

## **종합 결론 및 추천 전략**

보고서의 분석 결과를 바탕으로, AI 기반 낙상 방지 시스템 구축을 위한 최적의 아키텍처는 다음과 같이 요약될 수 있습니다.

**1\. 하이브리드 전략(YOLO11 \+ MediaPipe)이 유리한 경우:**

가정 내 독거노인 보호와 같이 '단일 대상'을 대상으로 '매우 정밀한' 동작 분석이 필요한 환경에 적합합니다. 33개 키포인트와 깊이 정보를 통해 낙상 전조 증상(비틀거리거나 잡으려 하는 동작)을 포착하고, 풍부한 특징량을 바탕으로 높은 분류 정확도를 확보할 수 있습니다. 특히 연구용이나 의료 전문 모니터링 시스템에서 강력한 성능을 발휘합니다.

**2\. 단일 전략(YOLO11 Pose)이 유리한 경우:**

요양원, 병원 병동, 복지관 등 '다수 인원'이 섞여 있는 공용 공간에서 '빠르고 안정적인' 탐지가 최우선인 환경에 적합합니다. 파이프라인이 단순하여 시스템 구축 비용이 저렴하고, 다중 인원에 대한 객체 추적 기능이 기본 포함되어 있어 운영 효율성이 높습니다. 또한 엣지 장치의 자원 사용을 최소화하면서도 30 FPS 이상의 실시간 모니터링을 보장합니다.

**3\. 시스템 구축 시 필수 고려 사항:**

* **시계열 모델 결합:** 단순 좌표 추출에 그치지 말고 GRU나 LSTM을 결합하여 20프레임 내외의 동작 흐름을 분석함으로써 오경보를 줄여야 합니다.  
* **다중 모달리티 활용:** 영상 데이터의 한계를 보완하기 위해 음성 인식(비명 감지 또는 확인 대화)이나 레이더 센서와의 융합을 고려하십시오.  
* **개인정보 보호:** 모든 영상 처리는 온디바이스(On-device)에서 수행하고, 보호자에게는 낙상 시의 뼈대(Skeleton) 영상이나 텍스트 알람만 전송하도록 설계해야 합니다.

결론적으로, 현재의 기술 수준에서 범용적인 낙상 방지 시스템을 구축하고자 한다면 **YOLO11 Pose 단일 체계**가 구현 난이도와 속도, 다중 인원 대응 측면에서 더 높은 실용성을 제공합니다. 그러나 특정 개인의 재활이나 정밀 의료 데이터를 목적으로 한다면 **YOLO11 \+ MediaPipe 하이브리드** 방식이 제공하는 세밀한 데이터가 더 큰 통찰력을 줄 수 있을 것입니다. 향후 YOLO26과 같은 차세대 모델의 도입은 이러한 전략들 간의 성능 간극을 더욱 좁히며, 더욱 지능적이고 신뢰할 수 있는 실버 케어 생태계를 조성하는 데 기여할 것입니다.

#### **참고 자료**

1. Towards safer environments: A YOLO and MediaPipe-based human ..., 2월 6, 2026에 액세스, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12475850/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12475850/)  
2. Next-generation fall detection: harnessing human pose estimation and transformer technology \- PMC \- PubMed Central, 2월 6, 2026에 액세스, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12107650/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12107650/)  
3. YOLO11 vs. YOLOv8: The Evolution of Real-Time Object Detection, 2월 6, 2026에 액세스, [https://docs.ultralytics.com/compare/yolo11-vs-yolov8/](https://docs.ultralytics.com/compare/yolo11-vs-yolov8/)  
4. Ultralytics YOLOv8 vs. YOLO11: Architectural Evolution and Performance Analysis, 2월 6, 2026에 액세스, [https://docs.ultralytics.com/compare/yolov8-vs-yolo11/](https://docs.ultralytics.com/compare/yolov8-vs-yolo11/)  
5. Real-time Fall Detection Prototyping with YOLOv11 Using an ..., 2월 6, 2026에 액세스, [https://oaji.net/pdf.html?n=2025/3603-1768745774.pdf](https://oaji.net/pdf.html?n=2025/3603-1768745774.pdf)  
6. Best Pose Estimation Models & How to Deploy Them, 2월 6, 2026에 액세스, [https://blog.roboflow.com/best-pose-estimation-models/](https://blog.roboflow.com/best-pose-estimation-models/)  
7. Comparing MediaPipe (CVZone) and YOLOPose for Real Time Pose Classification \- Reddit, 2월 6, 2026에 액세스, [https://www.reddit.com/r/computervision/comments/1lu60h5/comparing\_mediapipe\_cvzone\_and\_yolopose\_for\_real/](https://www.reddit.com/r/computervision/comments/1lu60h5/comparing_mediapipe_cvzone_and_yolopose_for_real/)  
8. On the Utility of Pose Estimation Models for Golf Swing Understanding, 2월 6, 2026에 액세스, [https://www.scirp.org/journal/paperinformation?paperid=148105](https://www.scirp.org/journal/paperinformation?paperid=148105)  
9. Pose Detection Showdown: BlazePose, MoveNet & YOLOv11 | Kite Metric, 2월 6, 2026에 액세스, [https://kitemetric.com/blogs/open-source-pose-detection-a-deep-dive-into-blazepose-movenet-and-yolov11](https://kitemetric.com/blogs/open-source-pose-detection-a-deep-dive-into-blazepose-movenet-and-yolov11)  
10. Real-Time Fall Monitoring for Seniors via YOLO and Voice Interaction \- MDPI, 2월 6, 2026에 액세스, [https://www.mdpi.com/1999-5903/17/8/324](https://www.mdpi.com/1999-5903/17/8/324)  
11. Improving Gesture Recognition Efficiency with MediaPipe and YOLO-Pose, 2월 6, 2026에 액세스, [https://isprs-archives.copernicus.org/articles/XLVIII-2-W9-2025/13/2025/isprs-archives-XLVIII-2-W9-2025-13-2025.pdf](https://isprs-archives.copernicus.org/articles/XLVIII-2-W9-2025/13/2025/isprs-archives-XLVIII-2-W9-2025-13-2025.pdf)  
12. Hybrid Architecture for Automatic Video-Based Fall Detection Using YOLOv11, MediaPipe Pose, and LSTM Networks \- ResearchGate, 2월 6, 2026에 액세스, [https://www.researchgate.net/publication/398433707\_Hybrid\_Architecture\_for\_Automatic\_Video-Based\_Fall\_Detection\_Using\_YOLOv11\_MediaPipe\_Pose\_and\_LSTM\_Networks](https://www.researchgate.net/publication/398433707_Hybrid_Architecture_for_Automatic_Video-Based_Fall_Detection_Using_YOLOv11_MediaPipe_Pose_and_LSTM_Networks)  
13. Hybrid Architecture for Automatic Video-Based ... \- Research Square, 2월 6, 2026에 액세스, [https://assets-eu.researchsquare.com/files/rs-8273858/v1\_covered\_cfc42e9b-525b-4aa2-86e1-f29b5e752317.pdf](https://assets-eu.researchsquare.com/files/rs-8273858/v1_covered_cfc42e9b-525b-4aa2-86e1-f29b5e752317.pdf)  
14. Mediapipe (via CVZone) vs. Ultralytics YOLOPose for Real Time Pose Classification: More Landmarks \= Better Inference : r/learnmachinelearning \- Reddit, 2월 6, 2026에 액세스, [https://www.reddit.com/r/learnmachinelearning/comments/1lf2aov/mediapipe\_via\_cvzone\_vs\_ultralytics\_yolopose\_for/](https://www.reddit.com/r/learnmachinelearning/comments/1lf2aov/mediapipe_via_cvzone_vs_ultralytics_yolopose_for/)  
15. OpenPose vs MediaPipe: Comprehensive Comparison & Analysis \- Saiwa, 2월 6, 2026에 액세스, [https://saiwa.ai/blog/openpose-vs-mediapipe/](https://saiwa.ai/blog/openpose-vs-mediapipe/)  
16. MediaPipe Vs YOLOv7 \- QuickPose.ai, 2월 6, 2026에 액세스, [https://quickpose.ai/faqs/mediapipe-vs-yolov7/](https://quickpose.ai/faqs/mediapipe-vs-yolov7/)  
17. A High-Precision Human Fall Detection Model Based on FasterNet and Deformable Convolution \- MDPI, 2월 6, 2026에 액세스, [https://www.mdpi.com/2079-9292/13/14/2798](https://www.mdpi.com/2079-9292/13/14/2798)  
18. Real-Time Fall Monitoring for Seniors via YOLO and Voice Interaction, 2월 6, 2026에 액세스, [https://www.mdpi.com/1999-5903/17/8/324/](https://www.mdpi.com/1999-5903/17/8/324/)  
19. rhafaelc/Fall-Detection-YOLO-MediaPipe \- GitHub, 2월 6, 2026에 액세스, [https://github.com/rhafaelc/Fall-Detection-YOLO-MediaPipe](https://github.com/rhafaelc/Fall-Detection-YOLO-MediaPipe)  
20. Fall Detection Using Deep Learning | by Erik Garcia \- Medium, 2월 6, 2026에 액세스, [https://medium.com/@erik172/fall-detection-using-deep-learning-2941db4c95a3](https://medium.com/@erik172/fall-detection-using-deep-learning-2941db4c95a3)  
21. A New Method for Real-Time Fall Detection Based on MediaPipe Pose Estimation and LSTM, 2월 6, 2026에 액세스, [https://thesai.org/Downloads/Volume16No8/Paper\_11-A\_New\_Method\_for\_Real\_Time\_Fall\_Detection.pdf](https://thesai.org/Downloads/Volume16No8/Paper_11-A_New_Method_for_Real_Time_Fall_Detection.pdf)  
22. YOLO11 vs YOLOv8: Model Comparison \- Labellerr, 2월 6, 2026에 액세스, [https://www.labellerr.com/blog/yolo11-vs-yolov8-model-comparison/](https://www.labellerr.com/blog/yolo11-vs-yolov8-model-comparison/)  
23. 대구광역시 AI상담서비스 시범운영, 2월 6, 2026에 액세스, [https://www.daegu.go.kr/120/customer/pressView.do;jsessionid=35A336C9E96424810C4979882CB47763?num=259\&curPage=1\&scType=\&scText=](https://www.daegu.go.kr/120/customer/pressView.do;jsessionid=35A336C9E96424810C4979882CB47763?num=259&curPage=1&scType&scText)  
24. 좋은선린병원, 대구·경북 최초 AI 스마트 병상 시스템 '씽크(thynC)' 도입…환자 안전 및 효율성 강화, 2월 6, 2026에 액세스, [https://www.benews.co.kr/news/442211](https://www.benews.co.kr/news/442211)  
25. AI 기반 신기술 복지용구 확대로 낙상 사고 막고 복약 누락 예방한다, 2월 6, 2026에 액세스, [https://www.korea.kr/common/download.do?fileId=198342141\&tblKey=GMN](https://www.korea.kr/common/download.do?fileId=198342141&tblKey=GMN)  
26. AI 기반 신기술 복지용구 확대…낙상 사고 막고 복약 누락 예방 \- 메디컬월드뉴스, 2월 6, 2026에 액세스, [https://medicalworldnews.co.kr/news/view.php?idx=1510972710](https://medicalworldnews.co.kr/news/view.php?idx=1510972710)  
27. 산업 현장에 스며든 AI 안전 기술…대구 기업들 예방 경쟁 \- 매일신문, 2월 6, 2026에 액세스, [https://www.imaeil.com/page/view/2026012700321414280](https://www.imaeil.com/page/view/2026012700321414280)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAYCAYAAAD3Va0xAAAA2ElEQVR4XmNgGAVDHzQB8SMg/g/FX6B8FiQ195Hk/wJxLpIcBoApxAbygXgPuiA2IMgAMeQ0ugQDRMwVXRAXiGaAGASiYYAViP8BMTeSGEEAshVkEMhlIKDHAAknkgFy+PRB2ScQ0sQBWPgcBuLXQKwG5YMwJ5I6ggAWPqBoZYaKNUDFWqF8ogAsfHiQxEBpCF9ywApwaQCFEUjcA10CGxBhgCg+gCYOAooMELn36BLYQA4DRHEQugQUwFyrgS4BA1sYEIqQMQdUXh7Kh+U7EPsJVG4UDAQAAMk+PRp7q9KvAAAAAElFTkSuQmCC>